"""Phase 1 proof of concept: detect the iPhone, list the photos, copy with verification,
and delete a few throwaway photos to check how the iPhone reacts.

    python -m safemove.probe                interactive menu (newest month folder)
    python -m safemove.probe --scan         read-only summary, no questions asked
    add --all (every folder, ~30 min) or --oldest (oldest month folder); default is the newest month

Everything shown is also written to C:\\SafeMove\\_probe\\probe-log.txt.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
from collections import Counter
from pathlib import Path

from .copier import CopyResult, verified_copy
from .wpd import DeviceError, DeviceFile, IPhone

PROBE_DIR = Path(r"C:\SafeMove\_probe")


class Probe:
    def __init__(self) -> None:
        PROBE_DIR.mkdir(parents=True, exist_ok=True)
        self.log = open(PROBE_DIR / "probe-log.txt", "a", encoding="utf-8")
        self.phone: IPhone | None = None
        self.files: list[DeviceFile] = []
        self.shown: list[DeviceFile] = []
        self.verified: dict[str, CopyResult] = {}  # object id -> successful copy this session

    # ---- console + log ----------------------------------------------------

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.log.write(text + "\n")
        self.log.flush()

    def ask(self, prompt: str) -> str:
        answer = input(prompt).strip()
        self.log.write(prompt + answer + "\n")
        return answer

    # ---- actions ----------------------------------------------------------

    def connect(self, interactive: bool) -> bool:
        while True:
            try:
                self.phone = IPhone.connect()
                self.say(f"✓ Connected: {self.phone.name}")
                return True
            except DeviceError as e:
                self.say(f"✗ {e}")
                if not interactive or self.ask("Press Enter to retry, or type Q to quit: ").lower() == "q":
                    return False

    def scan(self, which: str = "all") -> None:
        """which: 'all' (slow, ~30 min), 'newest' (newest month folder) or 'oldest' (oldest month folder)."""
        folders = self.phone.photo_folders()
        if which == "newest":
            folders = dict(list(folders.items())[-1:])
        elif which == "oldest":
            folders = dict(list(folders.items())[:1])
        self.say(f"Scanning {'all ' + str(len(folders)) + ' folders' if which == 'all' else which + ' folder ' + ', '.join(folders.values())} (read-only)...")
        start = time.time()
        files = self.phone.list_files(on_progress=lambda n: print(f"  ... {n:,} files", flush=True), folders=folders)
        self.files = sorted(files, key=lambda f: (f.date or dt.datetime.max, f.folder, f.name))
        total = sum(max(f.size, 0) for f in self.files)
        self.say(f"  {sum(f.kind != 'sidecar' for f in self.files):,} photos/videos, {gb(total)}, "
                 f"scanned in {time.time() - start:.1f}s")
        skipped = self.phone.skipped
        self.say(f"  Images: {sum(f.kind == 'images' for f in self.files):,}   "
                 f"Videos: {sum(f.kind == 'videos' for f in self.files):,}   "
                 f"Edit files (.AAE): {sum(f.kind == 'sidecar' for f in self.files):,}   "
                 f"Ignored (left untouched): {sum(skipped.values()):,}"
                 + (f" ({', '.join(f'{e} {n:,}' for e, n in skipped.most_common())})" if skipped else ""))
        if not self.files:
            return
        dated = [f.date for f in self.files if f.date]
        self.say(f"  Oldest: {d(min(dated, default=None))}   Newest: {d(max(dated, default=None))}")
        self.say(f"  Without a date: {sum(f.date is None for f in self.files)}   "
                 f"Unknown size: {sum(f.size < 0 for f in self.files)}")
        folders = Counter(f.folder for f in self.files)
        self.say(f"  Folders: {len(folders)} ({', '.join(sorted(folders)[:3])} ... {sorted(folders)[-1]})")
        sizes: Counter[str] = Counter()
        counts = Counter(ext(f) for f in self.files)
        for f in self.files:
            sizes[ext(f)] += max(f.size, 0)
        self.say("  Types: " + ", ".join(f"{e} {n:,} ({gb(sizes[e])})" for e, n in counts.most_common()))

    def show(self, files: list[DeviceFile], title: str) -> None:
        self.shown = files
        self.say(f"--- {title} ---")
        self.say(f"{'#':>3}  {'Folder':<10} {'Name':<16} {'Size':>10}  {'Created':<19}  {'Modified':<19}")
        for i, f in enumerate(files, 1):
            mark = "  [copied ✓]" if f.object_id in self.verified else ""
            self.say(f"{i:>3}  {f.folder:<10} {f.name:<16} {gb(f.size):>10}  {d(f.created):<19}  {d(f.modified):<19}{mark}")

    def pick(self, prompt: str) -> list[DeviceFile]:
        picked = []
        for part in self.ask(prompt).replace(",", " ").split():
            if part.isdigit() and 1 <= int(part) <= len(self.shown):
                picked.append(self.shown[int(part) - 1])
            else:
                self.say(f"  ignored '{part}' (not a number from the list)")
        return picked

    def copy_selected(self) -> None:
        if not self.shown:
            self.say("Show a list first (1 or 2).")
            return
        for f in self.pick("Numbers to copy (e.g. 18 19 20): "):
            dest = PROBE_DIR / f"{f.folder}_{f.name}"
            dest.unlink(missing_ok=True)
            start = time.time()
            r = verified_copy(self.phone, f, dest)
            secs = max(time.time() - start, 0.001)
            if r.ok:
                self.verified[f.object_id] = r
                self.say(f"  ✓ {f.name}: {r.bytes_written:,} bytes, SHA-256 {r.sha256[:16]}…, "
                         f"{secs:.1f}s ({f.size / 2**20 / secs:.1f} MB/s) → {dest}")
            else:
                self.say(f"  ✗ {f.name}: {r.error}")

    def delete_selected(self) -> None:
        if not self.shown:
            self.say("Show a list first (1 or 2).")
            return
        picked = self.pick("Numbers to DELETE from the iPhone (must be copied first): ")
        allowed = [f for f in picked if f.object_id in self.verified]
        for f in picked:
            if f not in allowed:
                self.say(f"  skipped {f.name}: not copied and verified in this session")
        if not allowed:
            return
        self.say("About to PERMANENTLY delete from the iPhone: " + ", ".join(f.name for f in allowed))
        if self.ask("Type DELETE to confirm: ") != "DELETE":
            self.say("  cancelled")
            return
        for f in allowed:
            try:
                self.phone.delete(f)
                del self.verified[f.object_id]
                self.say(f"  ✓ deleted {f.name}")
            except DeviceError as e:
                self.say(f"  ✗ {e}")
        self.say("Now check the iPhone Photos app (grey thumbnails? Recently Deleted? Live Photo fully gone?), "
                 "then rescan (5).")

    # ---- main loops -------------------------------------------------------

    def run(self, scan_only: bool, which: str) -> None:
        self.say(f"===== SafeMove probe — {dt.datetime.now():%Y-%m-%d %H:%M:%S} =====")
        if not self.connect(interactive=not scan_only):
            return
        try:
            self.which = which
            self.scan(which)
            if scan_only:
                self.show(self.files[:10], "Oldest 10")
                self.show(self.files[-10:], "Newest 10 (bottom = most recent)")
                return
            self.menu()
        except DeviceError as e:
            self.say(f"✗ {e}")
        finally:
            self.phone.close()

    def menu(self) -> None:
        while True:
            self.say()
            self.say("[1] Newest 20   [2] Oldest 20   [3] Copy   [4] Delete   [5] Rescan   "
                     "[6] Open probe folder   [0] Quit")
            choice = self.ask("> ")
            if choice == "1":
                self.show(self.files[-20:], "Newest 20 (bottom = most recent)")
            elif choice == "2":
                self.show(self.files[:20], "Oldest 20")
            elif choice == "3":
                self.copy_selected()
            elif choice == "4":
                self.delete_selected()
            elif choice == "5":
                self.scan(self.which)
                self.shown = []
            elif choice == "6":
                os.startfile(PROBE_DIR)
            elif choice == "0":
                self.say("Bye.")
                return
            else:
                self.say("?")


def gb(n: int) -> str:
    if n < 0:
        return "?"
    return f"{n / 2**30:.2f} GB" if n >= 2**30 else f"{n / 2**20:.1f} MB"


def d(value: dt.datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else "-"


def ext(f: DeviceFile) -> str:
    return Path(f.name).suffix.upper() or "(none)"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    which = "all" if "--all" in sys.argv else "oldest" if "--oldest" in sys.argv else "newest"
    Probe().run(scan_only="--scan" in sys.argv, which=which)
