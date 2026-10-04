"""The engine: for each group, copy -> verify -> move into the archive -> delete from the iPhone.

Safety rules (see PLAN.md):
- A group's files are deleted from the iPhone only after EVERY file of the group is verified on disk.
- Nothing half-written ever reaches the archive: files land in .staging first, then are renamed.
- Phone disconnected or disk problem -> stop at once; the current group stays on the phone.
- Test mode never deletes.
- Edited items (IMG_E render / .AAE) are copied but never deleted: the iPhone restores them after a
  reconnect. They are listed in logs\edited-items-to-delete.txt for deletion in the Photos app.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .copier import hash_on_phone, verified_copy
from .grouping import ChunkPlan, MediaGroup
from .paths import group_kind, place, target_dir
from .drives import too_big_for, volume_of
from .records import EDITED_STATUS, Manifest, RunLog
from .model import DeviceError

GB = 1 << 30


@dataclass
class Options:
    root: Path
    test_mode: bool = True
    paranoid: bool = False
    min_free_bytes: int = 20 * GB


@dataclass
class Event:
    """Progress and messages for the UI. level: info | ok | warn | error."""
    level: str
    text: str
    bytes_done: int = 0
    bytes_total: int = 0
    files_done: int = 0
    files_total: int = 0
    current: str = ""


@dataclass
class Summary:
    outcome: str = "done"  # done | stopped | disconnected | disk error | not enough space | file system limit | destination not found
    files_moved: int = 0  # verified in the archive (copied now or found from an earlier run)
    bytes_moved: int = 0
    files_deleted: int = 0
    edited_kept: list[str] = field(default_factory=list)  # labels of edited groups left on the iPhone
    edited_total: int = 0  # all edited items waiting for manual deletion (every run so far)
    edited_list_path: Path | None = None
    groups_failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0
    log_path: Path | None = None


def free_space_problem(root: Path, chunk_bytes: int, min_free_bytes: int) -> str | None:
    """None if the chunk fits while keeping `min_free_bytes` free on the destination drive."""
    probe = root
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free - chunk_bytes < min_free_bytes:
        return (f"Not enough space: {free / GB:.1f} GB free, the chunk needs {chunk_bytes / GB:.1f} GB "
                f"and {min_free_bytes / GB:.0f} GB must stay free.")
    return None


class Mover:
    def __init__(self, phone, options: Options, on_event: Callable[[Event], None] | None = None,
                 stop: threading.Event | None = None):
        self.phone = phone
        self.opt = options
        self.on_event = on_event or (lambda e: None)
        self.stop = stop or threading.Event()
        self.staging = options.root / ".staging"
        self.manifest = Manifest(options.root / "logs" / "manifest.csv")

    # ---- helpers ----------------------------------------------------------

    def _emit(self, level: str, text: str, **progress) -> None:
        self.log.write(f"[{level}] {text}")
        self.on_event(Event(level, text, **progress))

    def clean_staging(self) -> None:
        """Anything left in .staging comes from an interrupted run, so it is incomplete by definition."""
        if self.staging.exists():
            shutil.rmtree(self.staging, ignore_errors=True)
        self.staging.mkdir(parents=True, exist_ok=True)

    # ---- main -------------------------------------------------------------

    def _drive_gone(self) -> bool:
        return not Path(self.opt.root.anchor or self.opt.root).exists()

    def _disk_error(self, f, detail) -> None:
        if self._drive_gone():
            self._emit("error", f"The destination drive ({self.opt.root.anchor[:2]}) was disconnected while saving "
                                f"{f.name}. Nothing was lost: everything not finished is still on the phone. "
                                f"Reconnect the drive and press Start.")
        else:
            self._emit("error", f"Disk problem while saving {f.name}: {detail}. Run stopped.")

    def run(self, plan: ChunkPlan) -> Summary:
        start = time.time()
        if self._drive_gone():
            text = f"Destination drive {self.opt.root.anchor[:2]} is not connected. Nothing was done."
            self.on_event(Event("error", text))
            return Summary(outcome="destination not found")
        self.log = RunLog(self.opt.root / "logs")
        s = Summary(log_path=self.log.path)
        total_bytes, total_files = plan.size, plan.file_count
        done_bytes = done_files = 0
        mode = "TEST MODE (nothing deleted)" if self.opt.test_mode else "MOVE (verified files are deleted from the phone)"
        self._emit("info", f"Start: {total_files} files, {total_bytes / GB:.2f} GB, {mode}")

        try:
            if problem := free_space_problem(self.opt.root, total_bytes, self.opt.min_free_bytes):
                s.outcome = "not enough space"
                self._emit("error", problem)
                return s
            volume = volume_of(self.opt.root)
            fs = volume.fs if volume else ""
            if too_big := too_big_for(fs, ((f.name, f.size) for g in plan.groups for f in g.files)):
                s.outcome = "file system limit"
                self._emit("error", f"The destination drive is {fs}, which can't store files of 4 GB or more. "
                                    f"{len(too_big)} file(s) in this selection are bigger "
                                    f"({', '.join(too_big[:5])}{'…' if len(too_big) > 5 else ''}). "
                                    f"Reformat the drive as exFAT or NTFS, or choose another destination.")
                return s
            self.clean_staging()

            for group in plan.groups:
                if self.stop.is_set():
                    s.outcome = "stopped"
                    self._emit("warn", "Stopped safely. Everything not moved yet is still on the iPhone.")
                    break

                def progress(current: str, extra: int = 0):
                    return dict(bytes_done=done_bytes + extra, bytes_total=total_bytes,
                                files_done=done_files, files_total=total_files, current=current)

                result = self._move_group(group, progress, s)
                done_bytes += group.size
                done_files += len(group.files)
                if result in ("disconnected", "disk error"):
                    s.outcome = result
                    break
        except Exception as e:  # unexpected bug: stop, report, never delete further
            s.outcome = "error"
            self._emit("error", f"Unexpected error, run stopped: {e!r}")
        finally:
            try:
                s.edited_list_path = self.opt.root / "logs" / "edited-items-to-delete.txt"
                s.edited_total = self.manifest.write_edited_list(s.edited_list_path)
            except OSError:
                pass
            if s.edited_kept:
                self._emit("warn", f"✎ {len(s.edited_kept)} edited item(s) are safe on the PC but stay on the "
                                   f"iPhone: delete them in the Photos app. List: {s.edited_list_path}")
            s.seconds = time.time() - start
            self._emit("info", f"End: {s.outcome}. {s.files_moved} files ({s.bytes_moved / GB:.2f} GB) verified "
                               f"on the PC, {s.files_deleted} deleted from the iPhone, "
                               f"{len(s.groups_failed)} groups failed, {s.seconds:.0f}s")
            self.log.close()
        return s

    def _move_group(self, group: MediaGroup, progress, s: Summary) -> str:
        """Returns 'ok', 'failed' (skip this group, continue), 'disconnected' or 'disk error' (stop the run)."""
        placed: list[tuple] = []  # (file, final path, sha256, already_there)
        kind = group_kind(group.files)
        group_bytes = 0
        for f in group.files:
            self.on_event(Event("info", "", **progress(f.name, group_bytes)))
            staged = self.staging / f"{uuid.uuid4().hex[:8]}_{f.name}"

            def on_bytes(n, _base=group_bytes):
                on_bytes.total += n
                self.on_event(Event("info", "", **progress(f.name, _base + on_bytes.total)))
            on_bytes.total = 0

            r = verified_copy(self.phone, f, staged, on_bytes)
            if not r.ok:
                s.groups_failed.append(group.label)
                if r.error_kind == "device":
                    self.log.write(f"[detail] {r.error}")
                    self._emit("error", f"iPhone disconnected while copying {f.name}. Nothing lost: "
                                        f"{group.label} is still on the iPhone. Reconnect, unlock, and press Start.")
                    return "disconnected"
                if r.error_kind == "disk":
                    self._disk_error(f, r.error)
                    return "disk error"
                self._emit("error", f"✗ {group.label}: {f.name} failed verification ({r.error}). "
                                    f"Kept on the iPhone; continuing with the next files.")
                return "failed"

            if self.opt.paranoid:
                try:
                    if hash_on_phone(self.phone, f) != r.sha256:
                        staged.unlink(missing_ok=True)
                        s.groups_failed.append(group.label)
                        self._emit("error", f"✗ {group.label}: second read of {f.name} differs. Kept on the iPhone.")
                        return "failed"
                except DeviceError as e:
                    staged.unlink(missing_ok=True)
                    s.groups_failed.append(group.label)
                    self._emit("error", f"iPhone disconnected ({e}). {group.label} is still on the iPhone.")
                    return "disconnected"

            try:
                folder = target_dir(self.opt.root, f, kind, group.date)
                folder.mkdir(parents=True, exist_ok=True)
                final, already = place(staged, r.sha256, folder, f.name)
                if already:
                    staged.unlink()
                else:
                    os.replace(staged, final)  # same drive: atomic rename
            except OSError as e:
                staged.unlink(missing_ok=True)
                s.groups_failed.append(group.label)
                self._disk_error(f, e)
                return "disk error"
            placed.append((f, final, r.sha256, already))
            group_bytes += max(f.size, 0)

        # Every file of the group is verified in the archive.
        order = {f.object_id: i for i, f in enumerate(group.deletion_order())}
        for f, final, sha, already in sorted(placed, key=lambda p: order[p[0].object_id]):
            s.files_moved += 1
            s.bytes_moved += max(f.size, 0)
            prefix = "already on PC, " if already else ""
            if self.opt.test_mode:
                status = prefix + "kept (test mode)"
            elif group.is_edited:
                status = prefix + EDITED_STATUS
            else:
                try:
                    self.phone.delete(f)
                    s.files_deleted += 1
                    status = prefix + "deleted"
                except DeviceError as e:
                    status = prefix + "delete failed"
                    s.warnings.append(f"{f.name}: {e}")
                    self._emit("warn", f"⚠ {f.name} is safe on the PC but could not be deleted from the iPhone "
                                       f"({e}). It will be recognized and deleted next time.")
            self.manifest.add(f.folder, f.name, final, f.size, sha, status)
        if group.is_edited and not self.opt.test_mode:
            s.edited_kept.append(group.label)
            self._emit("warn", f"✎ {group.label} (edited) copied + verified → {placed[0][1].parent}. "
                               f"Kept on the iPhone: delete it in the Photos app ({group.date:%Y-%m-%d %H:%M}).")
            return "ok"
        verb = "copied + verified" if self.opt.test_mode else "moved"
        self._emit("ok", f"✓ {group.label} {verb} → {placed[0][1].parent}")
        return "ok"


def describe(summary: Summary) -> str:
    when = dt.timedelta(seconds=round(summary.seconds))
    text = (f"{summary.outcome.upper()}: {summary.files_moved} files ({summary.bytes_moved / GB:.2f} GB) "
            f"safe on the PC, {summary.files_deleted} deleted from the iPhone, "
            f"{len(summary.groups_failed)} groups failed, in {when}")
    if summary.edited_kept:
        text += f". {len(summary.edited_kept)} edited item(s) kept on the iPhone"
    return text
