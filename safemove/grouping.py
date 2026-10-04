"""Group files that belong together, and pick the oldest groups for one chunk.

A Live Photo is IMG_0579.HEIC + IMG_0579.MOV; an edited video is IMG_0578.MOV + IMG_E0578.MOV + IMG_0578.AAE.
Such files are moved, and deleted, as one unit, so the phone never keeps half of a photo.
An .AAE edit file that has no photo/video next to it is dropped (never moved or deleted).

Edited items (an IMG_E render or an .AAE) are copied but NOT deleted: the iPhone does not really delete
them over USB (they reappear after a reconnect), so the user deletes them in the Photos app.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .model import DeviceFile

# IMG_0579, IMG_E0579 (edited), IMG_O0579 (original, older iOS)
_NUMBERED = re.compile(r"^IMG_[EO]?(\d+)", re.IGNORECASE)


def group_key(f: DeviceFile) -> tuple[str, str]:
    m = _NUMBERED.match(f.name)
    stem = m.group(1) if m else f.name.rsplit(".", 1)[0].upper()
    return f.folder, stem


@dataclass
class MediaGroup:
    key: tuple[str, str]
    files: list[DeviceFile] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(max(f.size, 0) for f in self.files)

    @property
    def media(self) -> list[DeviceFile]:
        return [f for f in self.files if f.kind in ("images", "videos")]

    @property
    def date(self) -> dt.datetime:
        """Capture date: from the photo/video, not from the .AAE (that one is the edit date)."""
        return min((f.date for f in self.media if f.date), default=dt.datetime.max)

    @property
    def is_edited(self) -> bool:
        return any(f.kind == "sidecar" or re.match(r"^IMG_E", f.name, re.IGNORECASE) for f in self.files)

    def deletion_order(self) -> list[DeviceFile]:
        """Edit files first (.AAE, then IMG_E renders), the original photo/video last."""
        def rank(f: DeviceFile) -> int:
            if f.kind == "sidecar":
                return 0
            return 1 if re.match(r"^IMG_E", f.name, re.IGNORECASE) else 2
        return sorted(self.files, key=lambda f: (rank(f), f.name))

    @property
    def label(self) -> str:
        return " + ".join(f.name for f in self.files)


def make_groups(files: Iterable[DeviceFile]) -> list[MediaGroup]:
    """Groups files, oldest group first."""
    groups: dict[tuple[str, str], MediaGroup] = {}
    for f in files:
        groups.setdefault(group_key(f), MediaGroup(group_key(f))).files.append(f)
    for g in groups.values():
        g.files.sort(key=lambda f: f.name)
    return sorted((g for g in groups.values() if g.media), key=lambda g: (g.date, g.key))


@dataclass
class ChunkPlan:
    groups: list[MediaGroup]
    folders_scanned: list[str]
    folders_total: int
    label: str = ""  # what was asked for, e.g. "month 2024-08"

    @property
    def size(self) -> int:
        return sum(g.size for g in self.groups)

    @property
    def file_count(self) -> int:
        return sum(len(g.files) for g in self.groups)

    @property
    def first_date(self) -> dt.datetime | None:
        return self.groups[0].date if self.groups else None

    @property
    def last_date(self) -> dt.datetime | None:
        return self.groups[-1].date if self.groups else None


_YYYYMM = re.compile(r"^(\d{4})(\d{2})")


def folder_month(folder_name: str) -> str | None:
    """'202408_a' -> '2024-08'; None for undated folder names (e.g. 100APPLE on older iOS)."""
    m = _YYYYMM.match(folder_name)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def available_months(phone) -> list[str]:
    """Months that have photo folders on the phone, oldest first. Instant: uses folder names only."""
    return sorted({m for n in phone.photo_folders().values() if (m := folder_month(n))})


def _next_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def _scan(phone, items, on_progress, already_kept) -> tuple[list[DeviceFile], list[str]]:
    files: list[DeviceFile] = []
    scanned: list[str] = []
    for folder_id, name in items:
        files += [f for f in phone.list_files(folders={folder_id: name})
                  if (f.folder, f.name, f.size) not in already_kept]
        scanned.append(name)
        if on_progress:
            on_progress(name, len(files))
    return files, scanned


def plan_period(phone, start: dt.date, end: dt.date, on_progress: Callable[[str, int], None] | None = None,
                already_kept: set[tuple[str, str, int]] = frozenset(), label: str = "") -> ChunkPlan:
    """All groups whose capture date is in [start, end), oldest first. No size limit.

    Only the folders of the months concerned are scanned, plus the FIRST folder of the following month,
    because a photo can be filed there (e.g. saved just after midnight). A busy month can have many
    folders (202410__, 202410_a … 202410_i); reading all of the next month's would be slow for nothing.
    Undated folder names (older iOS) are always scanned.
    """
    months = set()
    day = start
    while day < end:
        months.add(f"{day:%Y-%m}")
        day += dt.timedelta(days=1)
    items = list(phone.photo_folders().items())  # sorted by name = by age
    pick = [(fid, n) for fid, n in items if folder_month(n) in months or folder_month(n) is None]
    after = {_next_month(m) for m in months} - months
    for nxt in sorted(after):
        first = next(((fid, n) for fid, n in items if folder_month(n) == nxt), None)
        if first:
            pick.append(first)
    pick.sort(key=lambda item: item[1])
    files, scanned = _scan(phone, pick, on_progress, already_kept)
    groups = [g for g in make_groups(files) if start <= g.date.date() < end]
    return ChunkPlan(groups, scanned, len(items), label)


def month_range(ym: str) -> tuple[dt.date, dt.date]:
    """'2024-08' -> (2024-08-01, 2024-09-01)."""
    start = dt.date(int(ym[:4]), int(ym[5:7]), 1)
    nxt = _next_month(ym)
    return start, dt.date(int(nxt[:4]), int(nxt[5:7]), 1)


def day_summary(phone, ym: str, on_progress=None,
                already_kept: set[tuple[str, str, int]] = frozenset()) -> list[tuple[dt.date, int, int]]:
    """(day, file count, bytes) for each day of month `ym` that still has photos/videos on the phone."""
    days: dict[dt.date, list[int]] = {}
    for g in plan_period(phone, *month_range(ym), on_progress, already_kept).groups:
        d = days.setdefault(g.date.date(), [0, 0])
        d[0] += len(g.files)
        d[1] += g.size
    return [(day, n, size) for day, (n, size) in sorted(days.items())]


def make_plan(phone, selection: tuple[str, object], on_progress=None,
              already_kept: set[tuple[str, str, int]] = frozenset()) -> ChunkPlan:
    """selection: ('size', bytes) | ('month', 'YYYY-MM') | ('day', 'YYYY-MM-DD')."""
    kind, value = selection
    if kind == "month":
        return plan_period(phone, *month_range(value), on_progress, already_kept, label=f"month {value}")
    if kind == "day":
        day = dt.date.fromisoformat(value)
        return plan_period(phone, day, day + dt.timedelta(days=1), on_progress, already_kept, label=f"day {value}")
    plan = plan_chunk(phone, value, on_progress, already_kept)
    plan.label = f"oldest {value / 2**30:g} GB"
    return plan


def plan_chunk(phone, chunk_bytes: int, on_progress: Callable[[str, int], None] | None = None,
               already_kept: set[tuple[str, str, int]] = frozenset()) -> ChunkPlan:
    """Picks the oldest groups up to `chunk_bytes`, scanning only as many month folders as needed.

    Folders are scanned oldest first until they hold more than the chunk, plus one extra folder,
    because two folders can cover the same month and their dates can interleave.
    A group is never split; the first group is always taken, even if it is bigger than the chunk.
    `already_kept`: (folder, name, size) of edited files already safe on the PC; their groups are skipped.
    """
    items = list(phone.photo_folders().items())
    files: list[DeviceFile] = []
    scanned: list[str] = []
    extra_done = False
    for item in items:
        more, names = _scan(phone, [item], None, already_kept)
        files += more
        scanned += names
        if on_progress:
            on_progress(item[1], len(files))
        if sum(max(f.size, 0) for f in files) > chunk_bytes:
            if extra_done:
                break
            extra_done = True

    chosen: list[MediaGroup] = []
    total = 0
    for g in make_groups(files):
        if chosen and total + g.size > chunk_bytes:
            break
        chosen.append(g)
        total += g.size
    return ChunkPlan(chosen, scanned, len(items))
