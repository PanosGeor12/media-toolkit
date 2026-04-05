# Media Toolkit

Desktop app for image compression (→ WebP), video compression (H.265), and media downloading (yt-dlp).

Built with Python, Tkinter, Pillow, FFmpeg, and yt-dlp. Packages into a standalone executable via PyInstaller.

---

## Features

| Tab | What it does | Requires |
|-----|-------------|----------|
| **Image Compressor** | Batch convert JPG/PNG/BMP/TIFF → WebP with EXIF stripping, resizing, and quality control | Pillow (bundled) |
| **Video Compressor** | Batch compress videos to H.265/AAC MP4 with adjustable CRF quality | FFmpeg |
| **Downloader** | Download video or audio (MP3) from YouTube and other sites | yt-dlp |

- Cancel button on every operation
- Thread-safe logging with live output
- Startup dependency detection — missing tools disable their tabs with a warning
- Catppuccin Mocha dark theme
- File size reporting with compression ratios

---

## Running from Source

### Prerequisites

- Python 3.10+
- [FFmpeg](https://ffmpeg.org/download.html) (for video compression)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (for downloading)

### Install & Run

```bash
pip install Pillow
python -m src
```

FFmpeg and yt-dlp must be on your system PATH.

or 

Placed in a /vendor folder inside of project root

---

## Building a Standalone Executable

### 1. Install build dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate the app icon

```bash
python build_icon.py
```

This converts `src/icon.svg` → `src/icon.ico` (multi-resolution).

### 3. (Optional) Bundle FFmpeg and yt-dlp

Create a `vendor/` directory and place the executables inside:

```
vendor/
  ffmpeg.exe      # Windows
  yt-dlp.exe      # Windows
```

On Linux/Mac, use the binaries without `.exe`. The build will automatically include them.

If you skip this step, the app will look for FFmpeg/yt-dlp on the system PATH at runtime.

### 4. Build

```bash
# Folder distribution (recommended — faster startup)
python build.py

# Single-file exe (slower startup, but one file)
python build.py --onefile

# Clean previous artifacts first
python build.py --clean
```

Output lands in `dist/MediaToolkit/` (folder) or `dist/MediaToolkit.exe` (single-file).

---

## Project Structure

```
media-toolkit/
├── src/
│   ├── __init__.py
│   ├── __main__.py        # Entry point — dependency check + launch
│   ├── constants.py       # Config values, theme colors
│   ├── dependencies.py    # FFmpeg/yt-dlp detection logic
│   ├── gui.py             # Tkinter GUI with tabs
│   ├── workers.py         # Background job classes (image, video, download)
│   ├── icon.svg           # Source icon
│   └── icon.ico           # Generated icon (run build_icon.py)
├── vendor/                # (optional) Bundled FFmpeg + yt-dlp
├── build.py               # Automated build script
├── build_icon.py          # SVG → ICO converter
├── media_toolkit.spec     # PyInstaller spec file
├── requirements.txt
└── README.md
```

---

## Configuration

Edit `src/constants.py` to change defaults:

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_IMAGE_WIDTH` | 1920 | Images wider than this get resized |
| `IMAGE_QUALITY` | 85 | WebP quality for opaque images (1-100) |
| `MAX_VIDEO_WIDTH` | 1920 | Video scale limit |
| `DEFAULT_CRF` | 28 | Default H.265 quality (18=best, 40=smallest) |

---

## Notes

- Transparent images (PNG with alpha) are saved as lossless WebP to preserve transparency
- Video compression uses `-preset slow` and `-movflags +faststart` for web-optimized output
- The downloader defaults to `--no-playlist` to avoid accidentally downloading entire playlists
- On Windows, subprocess windows are hidden (`CREATE_NO_WINDOW`) so no console flashes appear
