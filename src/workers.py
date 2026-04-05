"""Background worker functions for image compression, video compression, and downloading."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, List, Optional

from PIL import Image

from .constants import (
    IMAGE_QUALITY,
    MAX_IMAGE_WIDTH,
    MAX_VIDEO_WIDTH,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
)


class JobState(Enum):
    IDLE = auto()
    RUNNING = auto()
    CANCELLING = auto()
    DONE = auto()
    CANCELLED = auto()
    ERROR = auto()


# ── Quality presets ─────────────────────────────────────────
class QualityPreset(str, Enum):
    HIGH     = "high"
    BALANCED = "balanced"
    SMALL    = "small"
    TINY     = "tiny"
    TARGET   = "target"  # two-pass bitrate control for a target file size

PRESET_CRF: dict[QualityPreset, int] = {
    QualityPreset.HIGH:     28,
    QualityPreset.BALANCED: 35,
    QualityPreset.SMALL:    42,
    QualityPreset.TINY:     50,
    # TARGET has no CRF — uses two-pass bitrate control
}


@dataclass
class JobResult:
    total: int = 0
    succeeded: int = 0
    failed: List[str] = field(default_factory=list)
    skipped: int = 0


LogFn = Callable[[str], None]


class CancellableJob:
    """Mixin providing a thread-safe cancel mechanism."""

    def __init__(self):
        self._state = JobState.IDLE
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None

    @property
    def state(self) -> JobState:
        with self._lock:
            return self._state

    @state.setter
    def state(self, value: JobState):
        with self._lock:
            self._state = value

    def cancel(self):
        with self._lock:
            if self._state == JobState.RUNNING:
                self._state = JobState.CANCELLING
                if self._process and self._process.poll() is None:
                    self._process.terminate()

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._state in (JobState.CANCELLING, JobState.CANCELLED)


# ─────────────────────────────────────────────
# IMAGE COMPRESSION
# ─────────────────────────────────────────────
class ImageCompressor(CancellableJob):
    def __init__(self, input_folder: str, output_folder: str, log: LogFn,
                 max_width: int = MAX_IMAGE_WIDTH, quality: int = IMAGE_QUALITY):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.log = log
        self.max_width = max_width
        self.quality = quality

    def run(self) -> JobResult:
        self.state = JobState.RUNNING
        result = JobResult()

        try:
            os.makedirs(self.output_folder, exist_ok=True)
        except OSError as e:
            self.log(f"Cannot create output folder: {e}")
            self.state = JobState.ERROR
            return result

        try:
            files = sorted(os.listdir(self.input_folder))
        except OSError as e:
            self.log(f"Cannot read input folder: {e}")
            self.state = JobState.ERROR
            return result

        image_files = [f for f in files if f.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)]
        result.total = len(image_files)

        if result.total == 0:
            self.log("No supported image files found in the input folder.")
            self.state = JobState.DONE
            return result

        self.log(f"Found {result.total} image(s). Starting compression...\n")

        for i, filename in enumerate(image_files, 1):
            if self.is_cancelled:
                self.log("\nCancelled by user.")
                self.state = JobState.CANCELLED
                return result

            input_path = os.path.join(self.input_folder, filename)
            output_name = os.path.splitext(filename)[0] + ".webp"
            output_path = os.path.join(self.output_folder, output_name)

            try:
                img = Image.open(input_path)

                # Strip EXIF by copying pixel data to a clean image
                img_clean = Image.new(img.mode, img.size)
                img_clean.putdata(list(img.getdata()))
                img = img_clean

                # Resize if wider than max
                if img.width > self.max_width:
                    ratio = self.max_width / img.width
                    new_h = int(img.height * ratio)
                    img = img.resize((self.max_width, new_h), Image.LANCZOS)

                # Handle transparency
                has_alpha = img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                )
                if has_alpha:
                    img = img.convert("RGBA")
                    save_kwargs = {"lossless": True, "quality": 100, "method": 6}
                else:
                    img = img.convert("RGB")
                    save_kwargs = {"quality": self.quality, "method": 6}

                img.save(output_path, "WEBP", **save_kwargs)

                # Report sizes
                in_size = os.path.getsize(input_path)
                out_size = os.path.getsize(output_path)
                ratio_pct = (1 - out_size / in_size) * 100 if in_size > 0 else 0
                self.log(
                    f"[{i}/{result.total}] {filename} → {output_name}  "
                    f"({_human_size(in_size)} → {_human_size(out_size)}, "
                    f"{ratio_pct:.0f}% smaller)"
                )
                result.succeeded += 1

            except Exception as e:
                self.log(f"[{i}/{result.total}] FAILED: {filename} — {e}")
                result.failed.append(filename)

        self.state = JobState.DONE
        self._log_summary(result)
        return result

    def _log_summary(self, result: JobResult):
        self.log(f"\nDone: {result.succeeded}/{result.total} succeeded.")
        if result.failed:
            self.log(f"Failed: {', '.join(result.failed)}")


# ─────────────────────────────────────────────
# VIDEO COMPRESSION
# ─────────────────────────────────────────────
class VideoCompressor(CancellableJob):
    def __init__(self, input_folder: str, output_folder: str,
                 ffmpeg_path: str, log: LogFn,
                 preset: QualityPreset = QualityPreset.BALANCED,
                 target_size_mb: float | None = None,
                 max_width: int = MAX_VIDEO_WIDTH):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.ffmpeg_path = ffmpeg_path
        self.log = log
        self.max_width = max_width
        self.preset = preset
        self.target_size_mb = target_size_mb

        # Resolve effective CRF from preset
        if preset is QualityPreset.TARGET:
            self.crf = None  # two-pass — CRF unused
        else:
            self.crf = PRESET_CRF[preset]

    def run(self) -> JobResult:
        self.state = JobState.RUNNING
        result = JobResult()

        try:
            os.makedirs(self.output_folder, exist_ok=True)
        except OSError as e:
            self.log(f"Cannot create output folder: {e}")
            self.state = JobState.ERROR
            return result

        try:
            files = sorted(os.listdir(self.input_folder))
        except OSError as e:
            self.log(f"Cannot read input folder: {e}")
            self.state = JobState.ERROR
            return result

        video_files = [f for f in files if f.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)]
        result.total = len(video_files)

        if result.total == 0:
            self.log("No supported video files found in the input folder.")
            self.state = JobState.DONE
            return result

        mode_label = (
            f"target={self.target_size_mb} MB"
            if self.preset is QualityPreset.TARGET
            else f"preset={self.preset.value}, CRF={self.crf}"
        )
        self.log(f"Found {result.total} video(s). {mode_label}. Starting...\n")

        for i, filename in enumerate(video_files, 1):
            if self.is_cancelled:
                self.log("\nCancelled by user.")
                self.state = JobState.CANCELLED
                return result

            input_path = os.path.join(self.input_folder, filename)
            output_name = os.path.splitext(filename)[0] + "_compressed.webm"
            output_path = os.path.join(self.output_folder, output_name)

            self.log(f"[{i}/{result.total}] Encoding {filename}...")

            try:
                if self.preset is QualityPreset.TARGET:
                    self._encode_two_pass(input_path, output_path, i, result.total)
                else:
                    self._encode_crf(input_path, output_path)

                if self.is_cancelled:
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                        except OSError:
                            pass
                    self.log("\nCancelled by user.")
                    self.state = JobState.CANCELLED
                    return result

                in_size = os.path.getsize(input_path)
                out_size = os.path.getsize(output_path)
                ratio_pct = (1 - out_size / in_size) * 100 if in_size > 0 else 0
                self.log(
                    f"[{i}/{result.total}] {filename} → {output_name}  "
                    f"({_human_size(in_size)} → {_human_size(out_size)}, "
                    f"{ratio_pct:.0f}% smaller)"
                )
                result.succeeded += 1

            except subprocess.CalledProcessError:
                self.log(f"[{i}/{result.total}] FAILED: {filename} — FFmpeg returned an error")
                result.failed.append(filename)
            except Exception as e:
                self.log(f"[{i}/{result.total}] FAILED: {filename} — {e}")
                result.failed.append(filename)
            finally:
                self._process = None

        self.state = JobState.DONE
        self._log_summary(result)
        return result

    # ── Encode strategies ───────────────────────────────────
    def _encode_crf(self, input_path: str, output_path: str) -> None:
        """Single-pass constant-quality encode."""
        cmd = [
            self.ffmpeg_path, "-i", input_path,
            "-c:v", "libvpx-vp9",
            "-crf", str(self.crf),
            "-b:v", "0",
            "-deadline", "good",
            "-cpu-used", "2",
            "-row-mt", "1",
            "-vf", f"scale='min({self.max_width},iw)':-2",
            "-c:a", "libopus", "-b:a", "128k",
            "-y",
            output_path,
        ]
        self._run_cmd(cmd)

    def _encode_two_pass(self, input_path: str, output_path: str,
                         idx: int, total: int) -> None:
        """Two-pass encode targeting a specific file size in MB."""
        target_mb = self.target_size_mb
        if not target_mb or target_mb <= 0:
            raise ValueError("target_size_mb must be a positive number for TARGET preset")

        duration = self._probe_duration(input_path)
        if duration <= 0:
            raise ValueError(f"Could not read duration for {os.path.basename(input_path)}")

        audio_kbps = 128
        total_kbps = (target_mb * 8 * 1024) / duration
        video_kbps = max(100, int(total_kbps - audio_kbps))
        self.log(f"[{idx}/{total}]   → targeting {video_kbps} kbps video over {duration:.1f}s")

        log_prefix = os.path.join(self.output_folder, "_ffmpeg2pass")

        for pass_num in (1, 2):
            if self.is_cancelled:
                return

            base_cmd = [
                self.ffmpeg_path, "-i", input_path,
                "-c:v", "libvpx-vp9",
                "-b:v", f"{video_kbps}k",
                "-pass", str(pass_num),
                "-passlogfile", log_prefix,
                "-deadline", "good",
                "-cpu-used", "2",
                "-row-mt", "1",
                "-vf", f"scale='min({self.max_width},iw)':-2",
            ]
            if pass_num == 1:
                self.log(f"[{idx}/{total}]   → pass 1/2 (analysis)...")
                cmd = base_cmd + ["-an", "-f", "null",
                                  "NUL" if sys.platform == "win32" else "/dev/null"]
            else:
                self.log(f"[{idx}/{total}]   → pass 2/2 (encoding)...")
                cmd = base_cmd + ["-c:a", "libopus", "-b:a", "128k", "-y", output_path]

            self._run_cmd(cmd)

        # Clean up VP9 two-pass log files
        for ext in ("-0.log", "-0.log.vpxenc", "-0.log.temp"):
            try:
                os.remove(log_prefix + ext)
            except FileNotFoundError:
                pass

    # ── Subprocess helpers ──────────────────────────────────
    def _run_cmd(self, cmd: list[str]) -> None:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creationflags,
        )
        for line in self._process.stdout:
            stripped = line.strip()
            if stripped.startswith("frame=") or stripped.startswith("size="):
                pass  # keep log clean
        self._process.wait()
        if self._process.returncode not in (0, None) and not self.is_cancelled:
            raise subprocess.CalledProcessError(self._process.returncode, cmd[0])

    def _probe_duration(self, input_path: str) -> float:
        """Get video duration in seconds via ffprobe."""
        ffprobe = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        cmd = [
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            out = subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, text=True,
                creationflags=creationflags,
            )
            return float(out.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            return 0.0

    def _log_summary(self, result: JobResult):
        self.log(f"\nDone: {result.succeeded}/{result.total} succeeded.")
        if result.failed:
            self.log(f"Failed: {', '.join(result.failed)}")


# ─────────────────────────────────────────────
# DOWNLOADER
# ─────────────────────────────────────────────
class MediaDownloader(CancellableJob):
    def __init__(self, url: str, output_folder: str, mode: str,
                 ytdlp_path: str, log: LogFn):
        super().__init__()
        self.url = url
        self.output_folder = output_folder
        self.mode = mode  # "audio" or "video"
        self.ytdlp_path = ytdlp_path
        self.log = log

    def run(self) -> JobResult:
        self.state = JobState.RUNNING
        result = JobResult(total=1)

        try:
            os.makedirs(self.output_folder, exist_ok=True)
        except OSError as e:
            self.log(f"Cannot create output folder: {e}")
            self.state = JobState.ERROR
            return result

        output_template = os.path.join(self.output_folder, "%(title)s.%(ext)s")

        if self.mode == "audio":
            cmd = [
                self.ytdlp_path,
                "-x", "--audio-format", "mp3",
                "--audio-quality", "0",
                "--no-playlist",
                "-o", output_template,
                self.url,
            ]
        else:
            cmd = [
                self.ytdlp_path,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--no-playlist",
                "-o", output_template,
                self.url,
            ]

        self.log(f"Downloading ({self.mode}): {self.url}\n")

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            for line in self._process.stdout:
                stripped = line.strip()
                if stripped:
                    self.log(stripped)
            self._process.wait()

            if self.is_cancelled:
                self.log("\nCancelled by user.")
                self.state = JobState.CANCELLED
                return result

            if self._process.returncode == 0:
                self.log(f"\nDownload complete → {self.output_folder}")
                result.succeeded = 1
            else:
                self.log("\nDownload failed — yt-dlp returned an error.")
                result.failed.append(self.url)

        except Exception as e:
            self.log(f"Error: {e}")
            result.failed.append(self.url)
        finally:
            self._process = None

        self.state = JobState.DONE if result.succeeded else JobState.ERROR
        return result


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"
