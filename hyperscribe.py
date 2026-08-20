#!/usr/bin/env python3
"""
HyperScribe: Native Modern Desktop Audiobook Studio
High-performance, async TTS engine with automatic binary audio stitcher.
"""

import os
import re
import sys
import shutil
import asyncio
import threading
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Generator

import customtkinter as ctk
from tkinter import filedialog, messagebox
import aiofiles

# Text Extraction Libraries
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from pypdf import PdfReader
import edge_tts

# Try importing imageio_ffmpeg for zero-config ffmpeg on Windows
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = shutil.which("ffmpeg")

# Set UI Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ==========================================
# DATA STRUCTURES
# ==========================================
@dataclass
class AudioConfig:
    voice: str = "en-US-ChristopherNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"
    concurrency: int = 10


@dataclass
class Chapter:
    title: str
    content: str
    index: int


# ==========================================
# PARSER & CHUNKER ENGINE
# ==========================================
class DocumentParser:
    @staticmethod
    def parse(file_path: Path) -> List[Chapter]:
        ext = file_path.suffix.lower()
        if ext == ".epub":
            return DocumentParser._parse_epub(file_path)
        elif ext == ".pdf":
            return DocumentParser._parse_pdf(file_path)
        elif ext in [".txt", ".md", ".html", ".htm"]:
            return DocumentParser._parse_flat_text(file_path)
        else:
            raise ValueError(f"Unsupported format: {ext}")

    @staticmethod
    def _clean_text(html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        return re.sub(r"\n\s*\n+", "\n\n", text).strip()

    @staticmethod
    def _parse_epub(file_path: Path) -> List[Chapter]:
        book = epub.read_epub(str(file_path), options={"ignore_ncx": False})
        chapters = []
        idx = 1
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                cleaned = DocumentParser._clean_text(item.get_content().decode("utf-8", errors="ignore"))
                if len(cleaned.strip()) > 150:
                    chapters.append(Chapter(title=f"Chapter {idx}", content=cleaned, index=idx))
                    idx += 1
        return chapters

    @staticmethod
    def _parse_pdf(file_path: Path) -> List[Chapter]:
        reader = PdfReader(str(file_path))
        full_text = [p.extract_text() for p in reader.pages if p.extract_text()]
        return DocumentParser._chunk_flat("\n\n".join(full_text))

    @staticmethod
    def _parse_flat_text(file_path: Path) -> List[Chapter]:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if file_path.suffix.lower() in [".html", ".htm"]:
            text = DocumentParser._clean_text(text)
        return DocumentParser._chunk_flat(text)

    @staticmethod
    def _chunk_flat(text: str, max_chars: int = 15000) -> List[Chapter]:
        paragraphs = text.split("\n\n")
        chapters = []
        buf, length, idx = [], 0, 1
        for p in paragraphs:
            buf.append(p)
            length += len(p)
            if length >= max_chars:
                chapters.append(Chapter(title=f"Section {idx}", content="\n\n".join(buf), index=idx))
                buf, length, idx = [], 0, idx + 1
        if buf:
            chapters.append(Chapter(title=f"Section {idx}", content="\n\n".join(buf), index=idx))
        return chapters


class NaturalChunker:
    @staticmethod
    def chunk(text: str, max_chunk_size: int = 1200) -> Generator[str, None, None]:
        sentences = re.split(r"(?<=[.?!])\s+", text)
        buffer, length = [], 0
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if length + len(s) > max_chunk_size and buffer:
                yield " ".join(buffer)
                buffer, length = [s], len(s)
            else:
                buffer.append(s)
                length += len(s) + 1
        if buffer:
            yield " ".join(buffer)


# ==========================================
# ROBUST AUDIO STITCHER (FFMPEG OR BINARY)
# ==========================================
def join_audio_files(input_files: List[Path], output_file: Path):
    """Losslessly merges MP3 streams with FFmpeg if available, or binary stream concat."""
    if FFMPEG_EXE and os.path.exists(FFMPEG_EXE):
        manifest = output_file.parent / f"manifest_{output_file.stem}.txt"
        with open(manifest, "w", encoding="utf-8") as f:
            for file in input_files:
                f.write(f"file '{file.resolve()}'\n")

        cmd = [
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0",
            "-i", str(manifest), "-c", "copy", str(output_file)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        manifest.unlink(missing_ok=True)
    else:
        # High-speed fallback: MP3 frames can be concatenated directly as binary
        with open(output_file, "wb") as outfile:
            for infile_path in input_files:
                with open(infile_path, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)


# ==========================================
# ASYNC AUDIO ENGINE
# ==========================================
class HyperAudioSynthesizer:
    def __init__(self, config: AudioConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.concurrency)

    async def _synthesize(self, text: str, out_path: Path):
        async with self.semaphore:
            tts = edge_tts.Communicate(
                text=text,
                voice=self.config.voice,
                rate=self.config.rate,
                pitch=self.config.pitch,
                volume=self.config.volume,
            )
            await tts.save(str(out_path))

    async def process_chapter(self, chapter: Chapter, temp_dir: Path, on_progress) -> Path:
        chunks = list(NaturalChunker.chunk(chapter.content))
        if not chunks:
            out = temp_dir / f"ch_{chapter.index}.mp3"
            out.touch()
            return out

        chunk_files = []
        tasks = []
        for idx, segment in enumerate(chunks):
            cf = temp_dir / f"ch_{chapter.index:04d}_{idx:04d}.mp3"
            chunk_files.append(cf)

            async def _task(s=segment, f=cf):
                await self._synthesize(s, f)
                on_progress()

            tasks.append(_task())

        await asyncio.gather(*tasks)

        # Merge chapter segments
        ch_out = temp_dir / f"chapter_{chapter.index:04d}.mp3"
        join_audio_files(chunk_files, ch_out)

        for f in chunk_files:
            f.unlink(missing_ok=True)

        return ch_out


# ==========================================
# MODERN GUI APPLICATION
# ==========================================
class HyperScribeApp(ctk.CTk):
    VOICES = [
        "en-US-ChristopherNeural (Male - US)",
        "en-US-GuyNeural (Male - US)",
        "en-US-JennyNeural (Female - US)",
        "en-US-AriaNeural (Female - US)",
        "en-GB-RyanNeural (Male - UK)",
        "en-GB-SoniaNeural (Female - UK)",
        "en-AU-WilliamNeural (Male - AU)",
        "en-IN-PrabhatNeural (Male - IN)",
        "es-ES-AlvaroNeural (Male - Spanish)",
        "fr-FR-HenriNeural (Male - French)",
        "de-DE-ConradNeural (Male - German)",
        "ja-JP-KeitaNeural (Male - Japanese)",
    ]

    def __init__(self):
        super().__init__()
        self.title("⚡ HyperScribe - High-Velocity Audiobook Engine")
        self.geometry("780x680")
        self.resizable(False, False)

        self.selected_file: Path = None
        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="⚡ HyperScribe Audiobook Studio", font=("Segoe UI", 22, "bold"))
        title.pack(pady=(15, 2))
        subtitle = ctk.CTkLabel(self, text="Convert EPUB, PDF, TXT, MD losslessly with high-concurrency neural TTS", font=("Segoe UI", 12), text_color="gray")
        subtitle.pack(pady=(0, 15))

        frame = ctk.CTkFrame(self)
        frame.pack(padx=20, pady=5, fill="both", expand=True)

        file_row = ctk.CTkFrame(frame, fg_color="transparent")
        file_row.pack(fill="x", padx=15, pady=10)
        self.file_label = ctk.CTkLabel(file_row, text="No eBook selected...", anchor="w", text_color="gray")
        self.file_label.pack(side="left", fill="x", expand=True, padx=(0, 10))
        btn_select = ctk.CTkButton(file_row, text="Browse eBook", width=120, command=self._select_file)
        btn_select.pack(side="right")

        v_frame = ctk.CTkFrame(frame, fg_color="transparent")
        v_frame.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(v_frame, text="Neural Voice:", width=100, anchor="w").pack(side="left")
        self.voice_combo = ctk.CTkComboBox(v_frame, values=self.VOICES, width=380)
        self.voice_combo.set(self.VOICES[0])
        self.voice_combo.pack(side="left", padx=10)
        btn_preview = ctk.CTkButton(v_frame, text="🔊 Test Voice", width=100, fg_color="#2b2b2b", hover_color="#3d3d3d", command=self._test_voice)
        btn_preview.pack(side="right")

        self.rate_slider = self._create_slider_row(frame, "Speed Rate (%):", -50, 100, 0, 5)
        self.pitch_slider = self._create_slider_row(frame, "Pitch (Hz):", -20, 20, 0, 1)
        self.concurrency_slider = self._create_slider_row(frame, "Parallel Streams:", 1, 32, 12, 1)

        self.status_label = ctk.CTkLabel(self, text="Ready to convert", font=("Segoe UI", 12))
        self.status_label.pack(pady=(12, 4))

        self.prog_bar = ctk.CTkProgressBar(self, width=720)
        self.prog_bar.set(0)
        self.prog_bar.pack(pady=4)

        self.btn_convert = ctk.CTkButton(
            self, text="🚀 Generate Complete Audiobook", height=45, font=("Segoe UI", 14, "bold"), command=self._start_conversion
        )
        self.btn_convert.pack(padx=20, pady=(15, 20), fill="x")

    def _create_slider_row(self, parent, label: str, from_: int, to: int, default: int, step: int):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=6)
        ctk.CTkLabel(row, text=label, width=130, anchor="w").pack(side="left")
        val_label = ctk.CTkLabel(row, text=str(default), width=40)
        slider = ctk.CTkSlider(
            row, from_=from_, to=to, number_of_steps=(to - from_) // step,
            command=lambda v: val_label.configure(text=f"{int(v)}")
        )
        slider.set(default)
        val_label.pack(side="right")
        slider.pack(side="left", fill="x", expand=True, padx=10)
        return slider

    def _select_file(self):
        f = filedialog.askopenfilename(
            filetypes=[("Ebooks & Documents", "*.epub *.pdf *.txt *.md *.html *.htm")]
        )
        if f:
            self.selected_file = Path(f)
            self.file_label.configure(text=self.selected_file.name, text_color="white")

    def _test_voice(self):
        voice = self.voice_combo.get().split(" ")[0]
        rate = f"{int(self.rate_slider.get()):+d}%"
        pitch = f"{int(self.pitch_slider.get()):+d}Hz"

        def _play():
            try:
                temp_audio = Path(tempfile.gettempdir()) / "preview_sample.mp3"
                comm = edge_tts.Communicate("HyperScribe voice synthesis test.", voice=voice, rate=rate, pitch=pitch)
                asyncio.run(comm.save(str(temp_audio)))
                if sys.platform == "win32":
                    os.startfile(temp_audio)
                else:
                    subprocess.run(["xdg-open", str(temp_audio)])
            except Exception as e:
                messagebox.showerror("Preview Error", str(e))

        threading.Thread(target=_play, daemon=True).start()

    def _start_conversion(self):
        if not self.selected_file or not self.selected_file.exists():
            messagebox.showwarning("No File", "Please select a readable eBook file first!")
            return

        out_path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            initialfile=f"{self.selected_file.stem}_audiobook.mp3",
            filetypes=[("MP3 Audio", "*.mp3")],
        )
        if not out_path:
            return

        self.btn_convert.configure(state="disabled", text="⏳ Synthesizing Audiobook...")
        threading.Thread(target=self._run_pipeline, args=(Path(out_path),), daemon=True).start()

    def _run_pipeline(self, output_path: Path):
        try:
            self.status_label.configure(text="📖 Parsing document structure...")
            chapters = DocumentParser.parse(self.selected_file)
            total_chunks = sum(len(list(NaturalChunker.chunk(c.content))) for c in chapters)

            if total_chunks == 0:
                raise ValueError("Extracted text was empty.")

            voice = self.voice_combo.get().split(" ")[0]
            rate = f"{int(self.rate_slider.get()):+d}%"
            pitch = f"{int(self.pitch_slider.get()):+d}Hz"
            concurrency = int(self.concurrency_slider.get())

            config = AudioConfig(voice=voice, rate=rate, pitch=pitch, concurrency=concurrency)
            synthesizer = HyperAudioSynthesizer(config)

            completed = 0
            def on_progress():
                nonlocal completed
                completed += 1
                pct = completed / total_chunks
                self.prog_bar.set(pct)
                self.status_label.configure(text=f"⚡ Synthesizing: {completed}/{total_chunks} chunks ({int(pct*100)}%)")

            with tempfile.TemporaryDirectory() as temp_dir:
                td = Path(temp_dir)
                chapter_files = []

                async def _exec():
                    for ch in chapters:
                        res = await synthesizer.process_chapter(ch, td, on_progress)
                        chapter_files.append(res)

                asyncio.run(_exec())

                self.status_label.configure(text="🎛️ Stitching master audiobook...")
                join_audio_files(chapter_files, output_path)

            self.status_label.configure(text="✅ Conversion Complete!")
            self.prog_bar.set(1.0)
            messagebox.showinfo("Success", f"Audiobook successfully created!\nSaved to: {output_path}")

        except Exception as e:
            messagebox.showerror("Processing Error", str(e))
            self.status_label.configure(text="❌ Error occurred during conversion.")
        finally:
            self.btn_convert.configure(state="normal", text="🚀 Generate Complete Audiobook")


if __name__ == "__main__":
    app = HyperScribeApp()
    app.mainloop()
