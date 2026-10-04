"""The destination drive: which disk it is, its file system, and how much space must stay free.

External drives can come back under another letter (E: today, F: tomorrow), so the destination's
volume serial number is remembered and the drive is looked up by it. FAT32 can't store files of
4 GB or more, which long 4K videos often are.
"""

from __future__ import annotations

import ctypes
import os
import string
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

GB = 1 << 30
FAT32_MAX_FILE = 4 * GB - 1  # largest file FAT32 can hold
_DRIVE_REMOVABLE = 2


@dataclass(frozen=True)
class Volume:
    root: str  # "E:\\"
    label: str  # e.g. "Samsung T7"; can be empty
    serial: int  # volume serial number: stays the same whatever the letter
    fs: str  # "NTFS", "exFAT", "FAT32"…
    removable: bool  # USB stick / SD card (USB SSDs often report as fixed)
    system: bool  # the Windows drive

    @property
    def letter(self) -> str:
        return self.root[:2]

    @property
    def external(self) -> bool:
        return not self.system

    def describe(self) -> str:
        kind = "Windows drive" if self.system else "external drive" if self.removable else "other drive"
        label = f" “{self.label}”" if self.label else ""
        return f"{self.letter}{label} ({self.fs}, {kind})"


def volume_of(path: str | Path) -> Volume | None:
    """The volume holding `path`, or None if its drive isn't connected."""
    anchor = Path(path).anchor
    if not anchor:
        return None
    root = anchor if anchor.endswith("\\") else anchor + "\\"
    label = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_ulong(0)
    k32 = ctypes.windll.kernel32
    old_mode = k32.SetErrorMode(1)  # SEM_FAILCRITICALERRORS: no "insert a disk" popups for empty card readers
    try:
        ok = k32.GetVolumeInformationW(root, label, 261, ctypes.byref(serial), None, None, fs, 261)
        drive_type = k32.GetDriveTypeW(root)
    finally:
        k32.SetErrorMode(old_mode)
    if not ok:
        return None
    system_drive = os.environ.get("SystemDrive", "C:").upper()
    return Volume(root=root.upper(), label=label.value, serial=serial.value, fs=fs.value,
                  removable=drive_type == _DRIVE_REMOVABLE, system=root[:2].upper() == system_drive)


def all_volumes() -> list[Volume]:
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    found = []
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i) and (v := volume_of(f"{letter}:\\")):
            found.append(v)
    return found


def relocate(destination: str, serial: int, volumes: Iterable[Volume] | None = None) -> str | None:
    """If the destination's drive came back under another letter, the destination on the new letter.
    None when nothing needs to change (or the drive isn't connected at all)."""
    if not serial or not destination:
        return None
    current = volume_of(destination) if volumes is None else next(
        (v for v in volumes if v.root[:2].upper() == Path(destination).anchor[:2].upper()), None)
    if current and current.serial == serial:
        return None
    for v in (all_volumes() if volumes is None else volumes):
        if v.serial == serial:
            return v.root + str(Path(destination)).removeprefix(Path(destination).anchor)
    return None


def min_free_bytes(volume: Volume | None, system_gb: float, other_gb: float) -> int:
    """Free space that must remain after a run: a big margin on the Windows drive, a small one elsewhere."""
    return int((system_gb if volume is None or volume.system else other_gb) * GB)


def too_big_for(fs: str, files: Iterable[tuple[str, int]]) -> list[str]:
    """Names of files the file system can't store (FAT/FAT32: 4 GB limit). `files`: (name, size)."""
    if not fs.upper().startswith("FAT"):
        return []
    return [name for name, size in files if size > FAT32_MAX_FILE]
