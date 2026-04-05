"""Main GUI for Media Toolkit — Catppuccin Mocha themed, thread-safe, with cancel support."""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from .constants import (
    APP_NAME, APP_VERSION, DEFAULT_GEOMETRY,
    WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH,
    COLOR_BASE, COLOR_BLUE, COLOR_GREEN, COLOR_OVERLAY,
    COLOR_RED, COLOR_SUBTEXT, COLOR_SURFACE, COLOR_TEXT,
    COLOR_YELLOW, COLOR_PEACH,
)
from .dependencies import DependencyStatus
from .workers import (
    CancellableJob, ImageCompressor, JobState,
    MediaDownloader, QualityPreset, VideoCompressor,
)


class App(tk.Tk):
    def __init__(self, deps: DependencyStatus):
        super().__init__()
        self.deps = deps
        self._log_queue: queue.Queue = queue.Queue()
        self._active_job: Optional[CancellableJob] = None

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(DEFAULT_GEOMETRY)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.configure(bg=COLOR_BASE)

        # Set icon if available
        self._set_icon()

        self._build_styles()
        self._build_ui()
        self._build_status_bar()

        # Log dependency status on startup
        self._log_to_active(deps.summary())

        # Start the queue-polling loop
        self._poll_log_queue()

    def _set_icon(self):
        """Set window icon from bundled or local icon."""
        try:
            if getattr(sys, "frozen", False):
                base = sys._MEIPASS
            else:
                base = os.path.dirname(os.path.abspath(__file__))
            ico_path = os.path.join(base, "icon.ico")
            if os.path.isfile(ico_path):
                self.iconbitmap(ico_path)
        except Exception:
            pass  # Non-critical

    def _build_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=COLOR_BASE, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_OVERLAY, foreground=COLOR_TEXT,
                        padding=[14, 6], font=("Segoe UI", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", COLOR_BLUE)],
                  foreground=[("selected", COLOR_BASE)])
        style.configure("TFrame", background=COLOR_BASE)
        style.configure("TLabel", background=COLOR_BASE, foreground=COLOR_TEXT,
                        font=("Segoe UI", 10))
        style.configure("TProgressbar", troughcolor=COLOR_OVERLAY,
                        background=COLOR_GREEN, thickness=4)

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.tab_images = ttk.Frame(notebook)
        self.tab_videos = ttk.Frame(notebook)
        self.tab_download = ttk.Frame(notebook)

        notebook.add(self.tab_images, text="  Image Compressor  ")
        notebook.add(self.tab_videos, text="  Video Compressor  ")
        notebook.add(self.tab_download, text="  Downloader  ")

        self._build_image_tab()
        self._build_video_tab()
        self._build_download_tab()

        # Disable tabs based on deps
        if not self.deps.ffmpeg_ok:
            notebook.tab(1, state="disabled")
        if not self.deps.ytdlp_ok:
            notebook.tab(2, state="disabled")

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=COLOR_SURFACE, height=28)
        bar.pack(fill="x", side="bottom", padx=10, pady=(0, 10))
        self.status_label = tk.Label(
            bar, text="Ready", bg=COLOR_SURFACE, fg=COLOR_SUBTEXT,
            font=("Segoe UI", 9), anchor="w", padx=8
        )
        self.status_label.pack(fill="x")

    def _set_status(self, text: str, color: str = COLOR_SUBTEXT):
        self.status_label.config(text=text, fg=color)

    # ── Shared widget builders ──────────────────────────────
    def _folder_row(self, parent, label: str, row: int) -> tk.StringVar:
        tk.Label(parent, text=label, bg=COLOR_BASE, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", padx=14, pady=6)
        var = tk.StringVar()
        entry = tk.Entry(parent, textvariable=var, width=42, bg=COLOR_OVERLAY,
                         fg=COLOR_TEXT, insertbackground="white", relief="flat",
                         font=("Segoe UI", 10))
        entry.grid(row=row, column=1, padx=6, pady=6, sticky="ew")
        btn = tk.Button(parent, text="Browse", bg=COLOR_BLUE, fg=COLOR_BASE,
                        relief="flat", cursor="hand2", font=("Segoe UI", 9),
                        activebackground="#7ba8e8", activeforeground=COLOR_BASE,
                        command=lambda: self._browse_folder(var))
        btn.grid(row=row, column=2, padx=6)
        parent.columnconfigure(1, weight=1)
        return var

    def _browse_folder(self, var: tk.StringVar):
        folder = filedialog.askdirectory()
        if folder:
            var.set(folder)

    def _log_box(self, parent, row: int) -> tk.Text:
        frame = tk.Frame(parent, bg=COLOR_BASE)
        frame.grid(row=row, column=0, columnspan=3, padx=14, pady=10, sticky="nsew")
        parent.rowconfigure(row, weight=1)

        box = tk.Text(frame, bg=COLOR_SURFACE, fg=COLOR_GREEN,
                      font=("Cascadia Code", 9), relief="flat", wrap="word",
                      state="disabled", borderwidth=0, padx=8, pady=8)
        scroll = ttk.Scrollbar(frame, command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return box

    def _action_row(self, parent, row: int, start_text: str, start_color: str,
                    start_cmd, cancel_cmd) -> tuple:
        frame = tk.Frame(parent, bg=COLOR_BASE)
        frame.grid(row=row, column=0, columnspan=3, pady=6)

        start_btn = tk.Button(
            frame, text=start_text, bg=start_color, fg=COLOR_BASE,
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            activebackground=start_color, command=start_cmd, padx=20, pady=4
        )
        start_btn.pack(side="left", padx=6)

        cancel_btn = tk.Button(
            frame, text="Cancel", bg=COLOR_RED, fg=COLOR_BASE,
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            activebackground=COLOR_RED, command=cancel_cmd, padx=14, pady=4,
            state="disabled"
        )
        cancel_btn.pack(side="left", padx=6)

        return start_btn, cancel_btn

    # ── Thread-safe logging ─────────────────────────────────
    def _log(self, box: tk.Text, msg: str):
        """Thread-safe: enqueue log message, GUI thread picks it up."""
        self._log_queue.put((box, msg))

    def _poll_log_queue(self):
        """Drain the queue on the main thread — runs every 50 ms."""
        try:
            while True:
                box, msg = self._log_queue.get_nowait()
                box.configure(state="normal")
                box.insert("end", msg + "\n")
                box.see("end")
                box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(50, self._poll_log_queue)

    def _log_to_active(self, msg: str):
        """Log to whichever log box is currently visible (first tab by default)."""
        self._log(self.img_log, msg)

    def _clear_log(self, box: tk.Text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.configure(state="disabled")

    # ── Job management ──────────────────────────────────────
    def _run_job(self, job: CancellableJob, start_btn: tk.Button,
                 cancel_btn: tk.Button, log_box: tk.Text):
        """Start a job in a background thread, manage button states."""
        if self._active_job and self._active_job.state == JobState.RUNNING:
            messagebox.showwarning("Busy", "Another task is already running. Cancel it first.")
            return

        self._clear_log(log_box)
        self._active_job = job
        start_btn.config(state="disabled")
        cancel_btn.config(state="normal")
        self._set_status("Working...", COLOR_YELLOW)

        def _worker():
            try:
                result = job.run()
                self.after(0, lambda: self._on_job_done(start_btn, cancel_btn, job))
            except Exception as e:
                self._log(log_box, f"\nUnexpected error: {e}")
                self.after(0, lambda: self._on_job_done(start_btn, cancel_btn, job))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_job_done(self, start_btn: tk.Button, cancel_btn: tk.Button,
                     job: CancellableJob):
        start_btn.config(state="normal")
        cancel_btn.config(state="disabled")
        state = job.state
        if state == JobState.CANCELLED:
            self._set_status("Cancelled", COLOR_RED)
        elif state == JobState.ERROR:
            self._set_status("Finished with errors", COLOR_RED)
        else:
            self._set_status("Done", COLOR_GREEN)
        self._active_job = None

    def _cancel_active(self):
        if self._active_job:
            self._active_job.cancel()
            self._set_status("Cancelling...", COLOR_YELLOW)

    # ── Image Tab ───────────────────────────────────────────
    def _build_image_tab(self):
        p = self.tab_images
        self.img_input = self._folder_row(p, "Input Folder:", 0)
        self.img_output = self._folder_row(p, "Output Folder:", 1)
        self.img_start, self.img_cancel = self._action_row(
            p, 2, "Start Compression", COLOR_GREEN,
            self._start_image_compress, self._cancel_active
        )
        self.img_log = self._log_box(p, 3)

    def _start_image_compress(self):
        src = self.img_input.get().strip()
        dst = self.img_output.get().strip()
        if not src or not dst:
            messagebox.showwarning("Missing", "Select both input and output folders.")
            return
        if not os.path.isdir(src):
            messagebox.showerror("Error", f"Input folder does not exist:\n{src}")
            return

        log = lambda msg: self._log(self.img_log, msg)
        job = ImageCompressor(src, dst, log)
        self._run_job(job, self.img_start, self.img_cancel, self.img_log)

    # ── Video Tab ───────────────────────────────────────────
    def _build_video_tab(self):
        p = self.tab_videos
        self.vid_input = self._folder_row(p, "Input Folder:", 0)
        self.vid_output = self._folder_row(p, "Output Folder:", 1)

        # Quality preset row
        tk.Label(p, text="Quality:", bg=COLOR_BASE, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", padx=14, pady=6)

        preset_frame = tk.Frame(p, bg=COLOR_BASE)
        preset_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=6)

        self.vid_preset_var = tk.StringVar(value=QualityPreset.BALANCED.value)

        preset_options = [
            (QualityPreset.HIGH,     "High",     "Best quality, larger files"),
            (QualityPreset.BALANCED, "Balanced", "Good quality/size trade-off"),
            (QualityPreset.SMALL,    "Small",    "Smaller files, decent quality"),
            (QualityPreset.TINY,     "Tiny",     "Smallest files, lower quality"),
            (QualityPreset.TARGET,   "Target Size", "Aim for a specific file size"),
        ]

        for preset_enum, label, tooltip in preset_options:
            rb = tk.Radiobutton(
                preset_frame, text=label, variable=self.vid_preset_var,
                value=preset_enum.value, bg=COLOR_BASE, fg=COLOR_TEXT,
                selectcolor=COLOR_OVERLAY, activebackground=COLOR_BASE,
                activeforeground=COLOR_TEXT, font=("Segoe UI", 9),
                command=self._on_preset_change,
            )
            rb.pack(side="left", padx=6)

        # Target size row (hidden by default)
        self.target_frame = tk.Frame(p, bg=COLOR_BASE)
        self.target_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=14, pady=2)
        self.target_frame.grid_remove()  # hidden initially

        tk.Label(self.target_frame, text="Target (MB):", bg=COLOR_BASE, fg=COLOR_PEACH,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        self.target_size_var = tk.StringVar(value="50")
        self.target_entry = tk.Entry(
            self.target_frame, textvariable=self.target_size_var, width=8,
            bg=COLOR_OVERLAY, fg=COLOR_TEXT, insertbackground="white",
            relief="flat", font=("Segoe UI", 10)
        )
        self.target_entry.pack(side="left")
        tk.Label(self.target_frame, text="MB per file (uses two-pass encoding)",
                 bg=COLOR_BASE, fg=COLOR_SUBTEXT,
                 font=("Segoe UI", 8)).pack(side="left", padx=8)

        self.vid_start, self.vid_cancel = self._action_row(
            p, 4, "Start Compression", COLOR_GREEN,
            self._start_video_compress, self._cancel_active
        )
        self.vid_log = self._log_box(p, 5)

    def _on_preset_change(self):
        """Show/hide the target size input based on preset selection."""
        if self.vid_preset_var.get() == QualityPreset.TARGET.value:
            self.target_frame.grid()
            self.target_entry.focus_set()
        else:
            self.target_frame.grid_remove()

    def _start_video_compress(self):
        src = self.vid_input.get().strip()
        dst = self.vid_output.get().strip()
        if not src or not dst:
            messagebox.showwarning("Missing", "Select both input and output folders.")
            return
        if not os.path.isdir(src):
            messagebox.showerror("Error", f"Input folder does not exist:\n{src}")
            return

        preset = QualityPreset(self.vid_preset_var.get())
        target_mb = None

        if preset is QualityPreset.TARGET:
            try:
                target_mb = float(self.target_size_var.get())
                if target_mb <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid", "Enter a valid target size in MB (e.g. 50).")
                return

        log = lambda msg: self._log(self.vid_log, msg)
        job = VideoCompressor(
            src, dst,
            ffmpeg_path=self.deps.ffmpeg_path,
            log=log,
            preset=preset,
            target_size_mb=target_mb,
        )
        self._run_job(job, self.vid_start, self.vid_cancel, self.vid_log)

    # ── Download Tab ────────────────────────────────────────
    def _build_download_tab(self):
        p = self.tab_download

        tk.Label(p, text="URL:", bg=COLOR_BASE, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=14, pady=6)
        self.dl_url = tk.StringVar()
        tk.Entry(p, textvariable=self.dl_url, width=52, bg=COLOR_OVERLAY,
                 fg=COLOR_TEXT, insertbackground="white", relief="flat",
                 font=("Segoe UI", 10)).grid(row=0, column=1, columnspan=2,
                                              padx=6, pady=6, sticky="ew")

        self.dl_output = self._folder_row(p, "Save To:", 1)

        tk.Label(p, text="Mode:", bg=COLOR_BASE, fg=COLOR_TEXT,
                 font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", padx=14, pady=6)
        self.dl_mode = tk.StringVar(value="video")
        mode_frame = tk.Frame(p, bg=COLOR_BASE)
        mode_frame.grid(row=2, column=1, sticky="w")
        for val, label in [("video", "Video (MP4)"), ("audio", "Audio (MP3)")]:
            tk.Radiobutton(mode_frame, text=label, variable=self.dl_mode, value=val,
                           bg=COLOR_BASE, fg=COLOR_TEXT, selectcolor=COLOR_OVERLAY,
                           activebackground=COLOR_BASE, activeforeground=COLOR_TEXT,
                           font=("Segoe UI", 10)).pack(side="left", padx=10)

        self.dl_start, self.dl_cancel = self._action_row(
            p, 3, "Start Download", COLOR_BLUE,
            self._start_download, self._cancel_active
        )
        self.dl_log = self._log_box(p, 4)

    def _start_download(self):
        url = self.dl_url.get().strip()
        dst = self.dl_output.get().strip()
        if not url:
            messagebox.showwarning("Missing", "Enter a URL to download.")
            return
        if not dst:
            messagebox.showwarning("Missing", "Select an output folder.")
            return

        log = lambda msg: self._log(self.dl_log, msg)
        job = MediaDownloader(url, dst, self.dl_mode.get(), self.deps.ytdlp_path, log)
        self._run_job(job, self.dl_start, self.dl_cancel, self.dl_log)
