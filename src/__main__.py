"""Entry point for Media Toolkit — checks dependencies, then launches GUI.

Works both as:
    python -m src          (package mode)
    python src/__main__.py (direct mode)
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox

# Support running directly (python __main__.py) in addition to python -m src
if __package__ is None or __package__ == "":
    _src_dir = os.path.dirname(os.path.abspath(__file__))
    _project_dir = os.path.dirname(_src_dir)
    if _project_dir not in sys.path:
        sys.path.insert(0, _project_dir)
    __package__ = "src"

from .dependencies import check_dependencies
from .gui import App


def main():
    # Dependency check (runs before GUI so we can show warnings)
    deps = check_dependencies()

    if not deps.ffmpeg_ok and not deps.ytdlp_ok:
        # Show a bare Tk messagebox, then let the app open anyway (image tab works)
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Missing Dependencies",
            "Neither FFmpeg nor yt-dlp were found.\n\n"
            "• Video compression requires FFmpeg\n"
            "• Downloading requires yt-dlp\n\n"
            "Image compression will still work.\n"
            "Install the missing tools and restart the app.",
        )
        root.destroy()

    app = App(deps)
    app.mainloop()


if __name__ == "__main__":
    main()
