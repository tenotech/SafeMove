"""SafeMove window.

    pythonw -m safemove.app

All iPhone work happens on one background thread (WPD/COM objects must stay on the thread that
created them); the window only talks to it through queues, so it never freezes.
"""

from __future__ import annotations

import ctypes
import os
import queue
import shutil
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import comtypes

from .drives import Volume, min_free_bytes, relocate, too_big_for, volume_of
from .grouping import ChunkPlan, available_months, day_summary, make_plan
from .mover import GB, Event, Mover, Options, Summary, describe
from .records import Manifest
from .settings import Settings
from .wpd import DeviceError, IPhone

COLORS = {"ok": "#1a7f37", "warn": "#b35900", "error": "#c62828", "info": "#333333", "muted": "#777777"}


# ---- background worker --------------------------------------------------------

class Worker(threading.Thread):
    """Owns the iPhone connection. Jobs in, messages (kind, payload) out."""

    def __init__(self, out: queue.Queue):
        super().__init__(daemon=True)
        self.jobs: queue.Queue = queue.Queue()
        self.out = out
        self.phone: IPhone | None = None
        self.stop_flag = threading.Event()

    def post(self, kind: str, payload=None) -> None:
        self.out.put((kind, payload))

    def run(self) -> None:
        comtypes.CoInitialize()
        while True:
            job, args = self.jobs.get()
            if job == "quit":
                break
            try:
                getattr(self, f"do_{job}")(*args)
            except DeviceError as e:
                self._drop()
                self.post("disconnected", str(e))
            except Exception as e:  # never let the worker die silently
                self._drop()
                self.post("failure", repr(e))
        self._drop()

    def _drop(self) -> None:
        if self.phone:
            self.phone.close()
            self.phone = None

    def _phone(self) -> IPhone:
        if self.phone is None:
            self.post("connecting")
            self.phone = IPhone.connect()
            self.post("connected", (self.phone.name, len(self.phone.photo_folders())))
        return self.phone

    @staticmethod
    def _kept(root: Path) -> set:
        return Manifest(root / "logs" / "manifest.csv").kept_edited()  # edited items already safe on the PC

    def _plan(self, phone: IPhone, selection: tuple, root: Path) -> ChunkPlan:
        return make_plan(phone, selection, on_progress=lambda f, n: self.post("scanning", (f, n)),
                         already_kept=self._kept(root))

    def do_plan(self, selection: tuple | None, root: Path) -> None:
        phone = self._phone()
        self.post("months", available_months(phone))
        if selection is not None:
            self.post("plan", (selection, self._plan(phone, selection, root)))

    def do_days(self, month: str, root: Path) -> None:
        self.post("days", (month, day_summary(self._phone(), month, already_kept=self._kept(root))))

    def do_run(self, selection: tuple, options: Options) -> None:
        phone = self._phone()
        self.stop_flag.clear()
        plan = self._plan(phone, selection, options.root)
        self.post("plan", (selection, plan))
        summary = Mover(phone, options, lambda e: self.post("event", e), self.stop_flag).run(plan)
        if summary.outcome == "disconnected":
            self._drop()
        self.post("finished", summary)


# ---- window -------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.messages: queue.Queue = queue.Queue()
        self.worker = Worker(self.messages)
        self.worker.start()

        self.connected = False
        self.running = False
        self.plan: ChunkPlan | None = None
        self.plan_job = None
        self.speed_samples: list[tuple[float, int]] = []

        root.title("SafeMove")
        try:
            root.iconbitmap(default=str(Path(__file__).parent / "app.ico"))
        except tk.TclError:
            pass
        root.minsize(640, 600)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self._load_settings_into_ui()
        self.follow_drive()
        self.refresh_space()
        self.request_plan(delay_ms=0)
        root.after(100, self.poll)
        root.after(3000, self.watch_drive)

    # ---- layout ----

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 4}
        frm = ttk.Frame(self.root, padding=8)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        # iPhone
        ttk.Label(frm, text="iPhone", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", **pad)
        self.phone_var = tk.StringVar(value="Connecting…")
        self.phone_lbl = ttk.Label(frm, textvariable=self.phone_var)
        self.phone_lbl.grid(row=0, column=1, sticky="w", **pad)
        self.connect_btn = ttk.Button(frm, text="Reconnect", command=lambda: self.request_plan(0))
        self.connect_btn.grid(row=0, column=2, sticky="e", **pad)

        # destination
        ttk.Label(frm, text="Destination", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", **pad)
        self.dest_var = tk.StringVar()
        dest = ttk.Entry(frm, textvariable=self.dest_var)
        dest.grid(row=1, column=1, sticky="ew", **pad)
        dest.bind("<FocusOut>", lambda e: self.on_settings_changed())
        ttk.Button(frm, text="Browse…", command=self.browse).grid(row=1, column=2, sticky="e", **pad)
        self.space_var = tk.StringVar()
        self.space_lbl = ttk.Label(frm, textvariable=self.space_var)
        self.space_lbl.grid(row=2, column=1, columnspan=2, sticky="w", padx=12)

        # what to move: oldest N GB, a whole month, or one day
        ttk.Label(frm, text="Move this time", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="nw", **pad)
        sel = ttk.Frame(frm)
        sel.grid(row=3, column=1, columnspan=2, sticky="w", **pad)
        self.mode_var = tk.StringVar(value="size")
        self.chunk_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.day_var = tk.StringVar()

        ttk.Radiobutton(sel, text="Oldest first, up to", value="size", variable=self.mode_var,
                        command=self.on_mode_changed).grid(row=0, column=0, sticky="w")
        size_row = ttk.Frame(sel)
        size_row.grid(row=0, column=1, sticky="w", pady=2)
        spin = ttk.Spinbox(size_row, from_=0.1, to=500, increment=1, width=7, textvariable=self.chunk_var,
                           command=self.on_settings_changed)
        spin.pack(side="left")
        spin.bind("<KeyRelease>", lambda e: self.on_settings_changed())
        ttk.Label(size_row, text="GB").pack(side="left", padx=6)

        ttk.Radiobutton(sel, text="Whole month", value="month", variable=self.mode_var,
                        command=self.on_mode_changed).grid(row=1, column=0, sticky="w")
        self.month_box = ttk.Combobox(sel, textvariable=self.month_var, state="readonly", width=10)
        self.month_box.grid(row=1, column=1, sticky="w", pady=2)
        self.month_box.bind("<<ComboboxSelected>>", lambda e: self.on_month_changed())

        ttk.Radiobutton(sel, text="One day", value="day", variable=self.mode_var,
                        command=self.on_mode_changed).grid(row=2, column=0, sticky="w")
        self.day_box = ttk.Combobox(sel, textvariable=self.day_var, state="readonly", width=34)
        self.day_box.grid(row=2, column=1, sticky="w", pady=2)
        self.day_box.bind("<<ComboboxSelected>>", lambda e: self.on_settings_changed())
        self.days_month = None  # month whose days are in day_box
        self.plan_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.plan_var, foreground=COLORS["muted"]).grid(
            row=4, column=1, columnspan=2, sticky="w", padx=12)

        # options
        self.test_var = tk.BooleanVar()
        self.paranoid_var = tk.BooleanVar()
        ttk.Checkbutton(frm, text="Test mode (copy only, don't delete from iPhone)", variable=self.test_var,
                        command=self.on_settings_changed).grid(row=5, column=1, columnspan=2, sticky="w", **pad)
        ttk.Checkbutton(frm, text="Paranoid verify (read each file twice from the iPhone, slower)",
                        variable=self.paranoid_var, command=self.on_settings_changed).grid(
            row=6, column=1, columnspan=2, sticky="w", padx=12)

        # buttons
        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=3, pady=10)
        self.start_btn = ttk.Button(btns, text="Start", command=self.start)
        self.start_btn.pack(side="left", padx=6, ipadx=12)
        self.stop_btn = ttk.Button(btns, text="Stop safely", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Open folder", command=self.open_folder).pack(side="left", padx=6)
        self.reason_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.reason_var, foreground=COLORS["warn"]).grid(
            row=8, column=0, columnspan=3)

        # banner (disconnects etc.)
        self.banner = tk.Label(frm, text="", bg=COLORS["error"], fg="white", font=("Segoe UI", 10, "bold"),
                               wraplength=600, justify="left", padx=8, pady=6)

        # progress
        self.progress = ttk.Progressbar(frm, maximum=1000)
        self.progress.grid(row=10, column=0, columnspan=3, sticky="ew", padx=12, pady=(8, 2))
        self.progress_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.progress_var).grid(row=11, column=0, columnspan=3, sticky="w", padx=12)
        self.current_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.current_var, foreground=COLORS["muted"]).grid(
            row=12, column=0, columnspan=3, sticky="w", padx=12)

        # log
        box = ttk.Frame(frm)
        box.grid(row=13, column=0, columnspan=3, sticky="nsew", padx=12, pady=8)
        frm.rowconfigure(13, weight=1)
        self.log = tk.Text(box, height=12, wrap="word", font=("Consolas", 9), state="disabled",
                           relief="solid", borderwidth=1)
        scroll = ttk.Scrollbar(box, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        for level, color in COLORS.items():
            self.log.tag_configure(level, foreground=color)

    # ---- settings ----

    def _load_settings_into_ui(self) -> None:
        s = self.settings
        self.dest_var.set(s.destination)
        self.chunk_var.set(f"{s.chunk_gb:g}")
        self.mode_var.set(s.mode if s.mode in ("size", "month", "day") else "size")
        self.month_var.set(s.month)
        self.day_var.set(s.day)
        self.test_var.set(s.test_mode)
        self.paranoid_var.set(s.paranoid)

    def chunk_bytes(self) -> int | None:
        try:
            gb = float(self.chunk_var.get().replace(",", "."))
            return int(gb * GB) if gb > 0 else None
        except ValueError:
            return None

    def selection(self) -> tuple | None:
        """('size', bytes) | ('month', 'YYYY-MM') | ('day', 'YYYY-MM-DD'), or None if incomplete."""
        mode = self.mode_var.get()
        if mode == "month":
            return ("month", self.month_var.get()) if len(self.month_var.get()) == 7 else None
        if mode == "day":
            day = self.day_var.get()[:10]
            return ("day", day) if len(day) == 10 and day.startswith(self.month_var.get()) else None
        cb = self.chunk_bytes()
        return ("size", cb) if cb else None

    def root_path(self) -> Path:
        return Path(self.dest_var.get() or r"C:\SafeMove")

    def on_settings_changed(self) -> None:
        s = self.settings
        s.destination = self.dest_var.get().strip()
        if (cb := self.chunk_bytes()) is not None:
            s.chunk_gb = cb / GB
        s.mode = self.mode_var.get()
        s.month = self.month_var.get()
        s.day = self.day_var.get()[:10]
        s.test_mode = self.test_var.get()
        s.paranoid = self.paranoid_var.get()
        if vol := volume_of(s.destination):  # remember the drive itself, to find it under another letter
            s.dest_volume_serial, s.dest_volume_label = vol.serial, vol.label
        s.save()
        self.refresh_space()
        self.request_plan()

    def on_mode_changed(self) -> None:
        if self.mode_var.get() == "day":
            self.request_days()
        self.on_settings_changed()

    def on_month_changed(self) -> None:
        self.day_var.set("")
        self.request_days()
        self.on_settings_changed()

    def request_days(self) -> None:
        """Loads the days of the selected month (with counts) into the day list."""
        month = self.month_var.get()
        if month and not self.running and self.days_month != month:
            self.day_box.configure(values=[f"loading {month}…"])
            self.worker.jobs.put(("days", (month, self.root_path())))

    def browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest_var.get() or "C:\\")
        if folder:
            self.dest_var.set(os.path.normpath(folder))
            self.on_settings_changed()

    def open_folder(self) -> None:
        if self.volume() is None:
            messagebox.showinfo("SafeMove", "The destination drive is not connected.")
            return
        dest = Path(self.dest_var.get())
        dest.mkdir(parents=True, exist_ok=True)
        os.startfile(dest)

    # ---- destination drive / free space / start conditions ----

    def volume(self) -> Volume | None:
        return volume_of(self.dest_var.get() or "C:\\")

    def margin_bytes(self, vol: Volume | None = None) -> int:
        return min_free_bytes(vol or self.volume(), self.settings.min_free_gb, self.settings.min_free_gb_other)

    def follow_drive(self) -> None:
        """An external drive can come back under another letter (E: -> F:): follow it."""
        old = self.dest_var.get()
        if not self.settings.dest_volume_serial and (vol := volume_of(old)):
            self.settings.dest_volume_serial, self.settings.dest_volume_label = vol.serial, vol.label
            self.settings.save()  # settings from before drives were remembered
        new = relocate(old, self.settings.dest_volume_serial)
        if new:
            self.dest_var.set(new)
            self.add_log("info", f"The destination drive is now {Path(new).anchor[:2]} "
                                 f"(was {Path(old).anchor[:2]}): destination updated to {new}")
            self.on_settings_changed()

    def watch_drive(self) -> None:
        """Every few seconds: notice a drive being plugged in, unplugged or given another letter."""
        if not self.running:
            self.follow_drive()
            self.refresh_space()
        self.root.after(3000, self.watch_drive)

    def refresh_space(self) -> None:
        vol = self.volume()
        if vol is None:
            label = self.settings.dest_volume_label
            name = Path(self.dest_var.get()).anchor[:2] or "?"
            self.space_var.set(f"Destination drive {name}{f' “{label}”' if label else ''} is not connected: plug it in")
            self.space_lbl.configure(foreground=COLORS["error"])
        else:
            free = shutil.disk_usage(vol.root).free
            need = self.plan.size if self.plan else (self.chunk_bytes() or 0) if self.mode_var.get() == "size" else 0
            margin = self.margin_bytes(vol)
            ok = free - need >= margin
            low = (50 if vol.system else 10) * GB
            color = COLORS["error"] if not ok else COLORS["warn"] if free < low else COLORS["ok"]
            text = f"{vol.describe()} · free space: {free / GB:.1f} GB"
            if not ok:
                text += f"  ✗ must keep {margin / GB:g} GB free after this run"
            if vol.fs.upper().startswith("FAT"):
                text += "  ⚠ FAT32: can't store files of 4 GB or more"
                color = COLORS["warn"] if ok else color
            self.space_var.set(text)
            self.space_lbl.configure(foreground=color)
        self.update_buttons()

    def start_problem(self) -> str | None:
        if self.running:
            return None
        if not self.connected:
            return "Connect and unlock the iPhone."
        if self.selection() is None:
            return {"size": "Enter a size in GB.", "month": "Choose a month.",
                    "day": "Choose a day."}[self.mode_var.get()]
        if not self.plan:
            return "Preparing the list of files…"
        if not self.plan.groups:
            return ("Nothing left to move for this " + self.mode_var.get() + "."
                    if self.mode_var.get() != "size" else "Nothing left to move: no photos or videos found.")
        vol = self.volume()
        if vol is None:
            return "Connect the destination drive."
        if shutil.disk_usage(vol.root).free - self.plan.size < self.margin_bytes(vol):
            return "Not enough free space on the destination drive."
        if big := too_big_for(vol.fs, ((f.name, f.size) for g in self.plan.groups for f in g.files)):
            return (f"{len(big)} file(s) are 4 GB or bigger and can't be stored on this {vol.fs} drive. "
                    "Choose another destination, or reformat the drive as exFAT.")
        return None

    def update_buttons(self) -> None:
        problem = self.start_problem()
        self.start_btn.configure(state="disabled" if self.running or problem else "normal")
        self.stop_btn.configure(state="normal" if self.running else "disabled")
        self.connect_btn.configure(state="disabled" if self.running else "normal")
        self.reason_var.set("" if self.running else problem or "")

    # ---- talking to the worker ----

    def request_plan(self, delay_ms: int = 700) -> None:
        """(Re)computes the next chunk, debounced so typing a size doesn't spam the iPhone."""
        if self.running:
            return
        if self.plan_job:
            self.root.after_cancel(self.plan_job)
        self.plan = None
        self.update_buttons()

        def go():
            self.plan_job = None
            if not self.running:  # selection None: only connect and load the month list
                self.worker.jobs.put(("plan", (self.selection(), self.root_path())))
        self.plan_job = self.root.after(delay_ms, go)

    def start(self) -> None:
        if self.start_problem():
            return
        test = self.test_var.get()
        if not test and not messagebox.askyesno(
                "Move and delete",
                f"Move {self.plan.label}: {self.plan.file_count:,} files ({self.plan.size / GB:.2f} GB) to "
                f"{self.dest_var.get()}?\n\nEach photo/video is DELETED from the iPhone right after its copy "
                "on this PC has been verified. This cannot be undone on the iPhone.", icon="warning"):
            return
        self.hide_banner()
        options = Options(Path(self.dest_var.get()), test_mode=test, paranoid=self.paranoid_var.get(),
                          min_free_bytes=self.margin_bytes())
        self.running = True
        self.speed_samples = []
        self.progress["value"] = 0
        self.update_buttons()
        self.worker.jobs.put(("run", (self.selection(), options)))

    def stop(self) -> None:
        self.worker.stop_flag.set()
        self.stop_btn.configure(state="disabled")
        self.add_log("warn", "Stopping after the current photo/video…")

    def on_close(self) -> None:
        if self.running and not messagebox.askyesno(
                "Quit", "A transfer is running. Stop it safely and quit?\n(The current file is finished first.)"):
            return
        self.worker.stop_flag.set()
        self.worker.jobs.put(("quit", ()))
        self.root.after(300 if self.running else 0, self.root.destroy)

    # ---- messages from the worker ----

    def poll(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                getattr(self, f"on_{kind}")(payload)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def on_connecting(self, _) -> None:
        self.phone_var.set("Connecting…")
        self.phone_lbl.configure(foreground=COLORS["muted"])

    def on_connected(self, payload) -> None:
        name, folders = payload
        self.connected = True
        self.hide_banner()
        self.phone_var.set(f"Connected: {name} · {folders} photo folders")
        self.phone_lbl.configure(foreground=COLORS["ok"])
        self.update_buttons()

    def on_disconnected(self, message: str) -> None:
        self.connected = False
        self.running = False
        self.plan = None
        self.plan_var.set("")
        self.phone_var.set("Not connected")
        self.phone_lbl.configure(foreground=COLORS["error"])
        self.show_banner(f"{message}\nConnect the cable, unlock the iPhone, tap Trust if asked, then press Reconnect.")
        self.update_buttons()

    def on_failure(self, message: str) -> None:
        self.running = False
        self.add_log("error", f"Unexpected problem: {message}")
        self.show_banner(f"Unexpected problem: {message}")
        self.update_buttons()

    def on_scanning(self, payload) -> None:
        folder, n = payload
        self.plan_var.set(f"Looking at {folder}… ({n:,} files so far)")

    def on_months(self, months: list[str]) -> None:
        self.month_box.configure(values=months)
        if months and self.month_var.get() not in months:
            self.month_var.set(months[0])  # oldest month by default
            self.day_var.set("")
            self.days_month = None
            if self.mode_var.get() != "size":
                self.on_month_changed()
        if self.mode_var.get() == "day":
            self.request_days()

    def on_days(self, payload) -> None:
        month, days = payload
        if month != self.month_var.get():
            return  # the user picked another month meanwhile
        self.days_month = month
        values = [f"{d:%Y-%m-%d}  ·  {n:,} files  ·  {size / GB:.2f} GB" for d, n, size in days]
        self.day_box.configure(values=values or ["(nothing left this month)"])
        current = self.day_var.get()[:10]
        match = next((v for v in values if v.startswith(current)), None) if current else None
        new = match or (values[0] if values else "")
        if new != self.day_var.get():
            self.day_var.set(new)
            if self.mode_var.get() == "day":
                self.on_settings_changed()

    def on_plan(self, payload) -> None:
        selection, plan = payload
        if selection != self.selection():
            return  # result for an older choice; a newer plan is on its way
        self.plan = plan
        if plan.groups:
            self.plan_var.set(f"→ {plan.file_count:,} files, {plan.size / GB:.2f} GB, "
                              f"{plan.first_date:%Y-%m-%d} → {plan.last_date:%Y-%m-%d}")
        else:
            self.plan_var.set("→ nothing to move")
        self.refresh_space()

    def on_event(self, e: Event) -> None:
        if e.text:
            self.add_log(e.level, e.text)
            if e.level == "error" and "disconnected" in e.text:
                self.show_banner(e.text)
        if e.bytes_total:
            self.progress["value"] = 1000 * e.bytes_done / e.bytes_total
            now = time.time()
            self.speed_samples = [(t, b) for t, b in self.speed_samples if now - t < 8] + [(now, e.bytes_done)]
            (t0, b0), (t1, b1) = self.speed_samples[0], self.speed_samples[-1]
            speed = (b1 - b0) / (t1 - t0) if t1 > t0 else 0
            eta = f" · ~{(e.bytes_total - e.bytes_done) / speed / 60:.0f} min left" if speed > 0 else ""
            self.progress_var.set(f"{e.bytes_done / GB:.2f} / {e.bytes_total / GB:.2f} GB   "
                                  f"({e.files_done:,} / {e.files_total:,} files)")
            self.current_var.set(f"Current: {e.current} · {speed / 2**20:.1f} MB/s{eta}")

    def on_finished(self, s: Summary) -> None:
        self.running = False
        self.current_var.set("")
        if s.outcome == "done":
            self.progress["value"] = 1000
        self.add_log("ok" if s.outcome == "done" and not s.groups_failed else "warn", describe(s))
        self.update_buttons()
        icon = "info" if s.outcome == "done" and not s.groups_failed and not s.warnings else "warning"
        extra = ""
        if s.groups_failed:
            extra += f"\n\nKept on the iPhone (failed): {len(s.groups_failed)}\n" + "\n".join(s.groups_failed[:10])
        if s.warnings:
            extra += f"\n\nWarnings: {len(s.warnings)} (see log)"
        if s.edited_kept:
            extra += (f"\n\n✎ {len(s.edited_kept)} edited item(s) were copied and verified but stay on the "
                      f"iPhone (the iPhone does not let edited items be deleted over USB). Delete them yourself "
                      f"in the Photos app. Waiting in total: {s.edited_total}.\nList: {s.edited_list_path}")
        vol = self.volume()
        if vol and vol.external and s.files_moved:
            hint = (f"Before unplugging drive {vol.letter}, use “Safely Remove Hardware” (USB icon in the "
                    "taskbar) so Windows finishes writing everything.")
            self.add_log("info", hint)
            extra += f"\n\n⏏ {hint}"
        messagebox.showinfo("SafeMove", describe(s) + extra + f"\n\nLog: {s.log_path}", icon=icon)
        if s.outcome != "disconnected":
            self.days_month = None  # day counts changed
            if self.mode_var.get() == "day":
                self.request_days()
            self.request_plan(0)  # show what's next

    # ---- small UI helpers ----

    def add_log(self, level: str, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {text}\n", level)
        self.log.see("end")
        self.log.configure(state="disabled")

    def show_banner(self, text: str) -> None:
        self.banner.configure(text=text)
        self.banner.grid(row=9, column=0, columnspan=3, sticky="ew", padx=12, pady=4)

    def hide_banner(self) -> None:
        self.banner.grid_remove()


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
    except (AttributeError, OSError):
        pass
    # One copy at a time: two windows talking to the same iPhone could get in each other's way.
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel32.CreateMutexW(None, False, "Local\\SafeMove.SingleInstance")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        tk.Tk().withdraw()
        messagebox.showinfo("SafeMove", "SafeMove is already open (look in the taskbar).")
        return
    root = tk.Tk()
    App(root)
    root.mainloop()
    kernel32.CloseHandle(ctypes.c_void_p(mutex))


if __name__ == "__main__":
    main()
