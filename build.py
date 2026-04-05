#!/usr/bin/env python3
"""
Build script for Media Toolkit.

Steps:
  1. Generate icon.ico from icon.svg  (if not present)
  2. Optionally copy FFmpeg/yt-dlp into vendor/
  3. Run PyInstaller with the .spec file

Usage:
    python build.py              # Normal folder build
    python build.py --onefile    # Single-file build
    python build.py --clean      # Clean previous build artifacts first
"""

import argparse
import os
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(HERE, "media_toolkit.spec")
ICON_ICO = os.path.join(HERE, "src", "icon.ico")
ICON_SCRIPT = os.path.join(HERE, "build_icon.py")


def step(msg: str):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


def run(cmd: list[str], **kwargs):
    print(f"  → {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"  ✗ Command failed with exit code {result.returncode}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Build Media Toolkit")
    parser.add_argument("--onefile", action="store_true", help="Build single-file exe")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts first")
    args = parser.parse_args()

    # 0. Clean
    if args.clean:
        step("Cleaning previous build artifacts")
        for d in ["build", "dist"]:
            path = os.path.join(HERE, d)
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path)
                print(f"  Removed {d}/")

    # 1. Generate icon
    if not os.path.isfile(ICON_ICO):
        step("Generating icon.ico from icon.svg")
        run([sys.executable, ICON_SCRIPT])
    else:
        print(f"\n  Icon already exists: {ICON_ICO}")

    # 2. Patch spec for --onefile if requested
    if args.onefile:
        step("Patching spec for single-file build")
        spec_content = open(SPEC_FILE).read()
        spec_content = spec_content.replace("one_file = False", "one_file = True")
        with open(SPEC_FILE, "w") as f:
            f.write(spec_content)
        print("  Set one_file = True in spec")

    # 3. Build with PyInstaller
    step("Running PyInstaller")
    run([sys.executable, "-m", "PyInstaller", SPEC_FILE, "--noconfirm"])

    # 4. Report
    step("Build complete")
    if args.onefile:
        exe_name = "MediaToolkit.exe" if sys.platform == "win32" else "MediaToolkit"
        print(f"  Output: dist/{exe_name}")
    else:
        print(f"  Output: dist/MediaToolkit/")
    print()

    # Restore spec if we patched it
    if args.onefile:
        spec_content = open(SPEC_FILE).read()
        spec_content = spec_content.replace("one_file = True", "one_file = False")
        with open(SPEC_FILE, "w") as f:
            f.write(spec_content)


if __name__ == "__main__":
    main()
