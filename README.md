<img width="2323" height="537" alt="Untitled Document 2 (1) (1) (5) (2)" src="https://github.com/user-attachments/assets/7fa0811c-34f1-47ce-a362-a6cb708cb7cd" />

# ⚡ HyperScribe

**A native, high-velocity desktop audiobook studio.** HyperScribe converts eBooks and documents (EPUB, PDF, TXT, MD, HTML) into narrated MP3 audiobooks using Microsoft Edge's neural text-to-speech voices — with async, high-concurrency synthesis and lossless audio stitching.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## ✨ Features

- **Multi-format ingestion** — Parses `.epub`, `.pdf`, `.txt`, `.md`, `.html`, and `.htm` files, automatically splitting content into chapters or sized sections.
- **Neural TTS voices** — Powered by `edge-tts`, with a curated set of natural-sounding voices across English (US/UK/AU/IN), Spanish, French, German, and Japanese.
- **High-concurrency synthesis** — Async pipeline with a configurable semaphore (1–32 parallel streams) for fast conversion of long texts.
- **Natural sentence chunking** — Splits text on sentence boundaries to keep TTS output sounding smooth, not choppy.
- **Lossless audio stitching** — Merges chapter/segment audio via `ffmpeg` (auto-detected, zero-config via `imageio-ffmpeg`) or falls back to raw binary MP3 concatenation if `ffmpeg` isn't available.
- **Modern dark-mode GUI** — Built with `customtkinter`: file picker, voice selector with live preview, and sliders for speed, pitch, and concurrency.
- **Live progress tracking** — Real-time chunk-by-chunk progress bar and status updates during synthesis.

## 🖥️ Requirements

- Python 3.9+
- An internet connection (Edge TTS is a cloud-based neural voice service)

### Python dependencies

```
customtkinter
aiofiles
ebooklib
beautifulsoup4
pypdf
edge-tts
imageio-ffmpeg
```

## 📦 Installation

```bash
git clone https://github.com/<your-username>/hyperscribe.git
cd hyperscribe
pip install -r requirements.txt
python hyperscribe.py
```

> `ffmpeg` is bundled automatically via `imageio-ffmpeg`. If it's unavailable on your system, HyperScribe falls back to direct binary MP3 concatenation.

## 🚀 Usage

1. Launch the app: `python hyperscribe.py`
2. Click **Browse eBook** and select an `.epub`, `.pdf`, `.txt`, `.md`, or `.html` file.
3. Choose a **Neural Voice** from the dropdown — use **🔊 Test Voice** to preview it first.
4. Adjust **Speed Rate**, **Pitch**, and **Parallel Streams** to taste.
5. Click **🚀 Generate Complete Audiobook** and choose where to save the output `.mp3`.
6. Watch the progress bar as chunks are synthesized and stitched into your final audiobook.

## ⚙️ Configuration Options

| Setting | Range | Description |
|---|---|---|
| Speed Rate | -50% to +100% | Adjusts narration speed |
| Pitch | -20Hz to +20Hz | Adjusts voice pitch |
| Parallel Streams | 1–32 | Number of concurrent TTS requests (higher = faster, but may hit rate limits) |

## 🏗️ How It Works

1. **Parsing** — `DocumentParser` extracts and cleans text from the source file, splitting it into `Chapter` objects (using EPUB spine items, PDF page text, or size-based sectioning for flat text formats).
2. **Chunking** — `NaturalChunker` breaks each chapter into sentence-aligned chunks (~1200 characters) suitable for TTS requests.
3. **Synthesis** — `HyperAudioSynthesizer` fires off async `edge-tts` requests, bounded by a semaphore for concurrency control.
4. **Stitching** — `join_audio_files` merges per-chunk MP3s into per-chapter files, then merges all chapters into the final audiobook, preferring `ffmpeg` concat for reliability.

<img width="1020" height="923" alt="image" src="https://github.com/user-attachments/assets/7bc62d11-8ce5-40af-9ad0-75a3465f73d1" />
<img width="1912" height="1102" alt="image" src="https://github.com/user-attachments/assets/338129ee-cc8f-4e67-81d4-f8050ec6824a" />
<img width="1919" height="1199" alt="image" src="https://github.com/user-attachments/assets/60c97e04-fa68-4904-a556-5490bdf08d34" />


## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

## ⚠️ Disclaimer

HyperScribe uses the Microsoft Edge TTS service. Please ensure you have the rights to convert any text you process, and review Microsoft's terms of service for `edge-tts` usage.
