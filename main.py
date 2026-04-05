"""
Top-level entry point — works in all three contexts:

  1. python main.py                  (run from source, direct)
  2. python -m src                   (run from source, package mode)
  3. PyInstaller frozen exe          (all modules are flat in sys.path)
"""

import os
import sys

# When running from source, ensure the project root is on sys.path
# so that `import src` resolves correctly.
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import tkinter as tk
from tkinter import messagebox

from src.dependencies import check_dependencies
from src.gui import App


def main():
    deps = check_dependencies()

    if not deps.ffmpeg_ok and not deps.ytdlp_ok:
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
