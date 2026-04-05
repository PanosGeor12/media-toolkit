"""Startup dependency checks for external tools (FFmpeg, yt-dlp)."""

import os
import shutil
import subprocess
import sys
from typing import Optional


def _get_bundled_dir() -> Optional[str]:
    """Return the PyInstaller bundle directory, or None if running from source."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "vendor")
    return None


def _find_executable(name: str) -> Optional[str]:
    """
    Locate an executable by checking:
      1. PyInstaller vendor/ bundle
      2. vendor/ next to the exe or project root
      3. Same directory as the running script/exe
      4. Project root (parent of src/)
      5. System PATH
    """
    exe_name = f"{name}.exe" if sys.platform == "win32" else name

    # 1. PyInstaller bundled vendor dir
    bundled = _get_bundled_dir()
    if bundled:
        path = os.path.join(bundled, exe_name)
        if os.path.isfile(path):
            return path

    # Determine key directories
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
        project_dir = app_dir
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))      # src/
        project_dir = os.path.dirname(app_dir)                     # media-toolkit/

    # 2. vendor/ subdirectory (next to exe, or at project root)
    for base in dict.fromkeys([app_dir, project_dir]):  # deduplicated, ordered
        vendor_path = os.path.join(base, "vendor", exe_name)
        if os.path.isfile(vendor_path):
            return vendor_path

    # 3. Same directory as the script/exe
    local_path = os.path.join(app_dir, exe_name)
    if os.path.isfile(local_path):
        return local_path

    # 4. Project root
    if project_dir != app_dir:
        root_path = os.path.join(project_dir, exe_name)
        if os.path.isfile(root_path):
            return root_path

    # 5. System PATH
    found = shutil.which(name)
    return found


def _check_version(executable: str) -> Optional[str]:
    """Run `executable -version` or `--version` and return first output line."""
    for flag in ["-version", "--version"]:
        try:
            result = subprocess.run(
                [executable, flag],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            output = (result.stdout or result.stderr or "").strip()
            if output:
                return output.splitlines()[0]
        except (subprocess.SubprocessError, OSError):
            continue
    return None


class DependencyStatus:
    """Holds the resolved paths and status of external dependencies."""

    def __init__(self):
        self.ffmpeg_path: Optional[str] = None
        self.ffmpeg_version: Optional[str] = None
        self.ytdlp_path: Optional[str] = None
        self.ytdlp_version: Optional[str] = None

    @property
    def ffmpeg_ok(self) -> bool:
        return self.ffmpeg_path is not None

    @property
    def ytdlp_ok(self) -> bool:
        return self.ytdlp_path is not None

    def summary(self) -> str:
        lines = []
        if self.ffmpeg_ok:
            lines.append(f"FFmpeg: {self.ffmpeg_version or 'found'}")
        else:
            lines.append("FFmpeg: NOT FOUND — video compression disabled")
        if self.ytdlp_ok:
            lines.append(f"yt-dlp: {self.ytdlp_version or 'found'}")
        else:
            lines.append("yt-dlp: NOT FOUND — downloader disabled")
        return "\n".join(lines)


def check_dependencies() -> DependencyStatus:
    """Locate FFmpeg and yt-dlp, return a status object."""
    status = DependencyStatus()

    status.ffmpeg_path = _find_executable("ffmpeg")
    if status.ffmpeg_path:
        status.ffmpeg_version = _check_version(status.ffmpeg_path)

    status.ytdlp_path = _find_executable("yt-dlp")
    if status.ytdlp_path:
        status.ytdlp_version = _check_version(status.ytdlp_path)

    return status
