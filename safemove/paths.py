"""Where each file goes: <root>\\images|videos\\YYYY\\MM\\<name>, with collision-safe names."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .copier import hash_file
from .model import DeviceFile


def group_kind(files: list[DeviceFile]) -> str:
    """A group with a photo goes to images\\ entirely: a Live Photo's .MOV stays next to its photo,
    and videos\\ only holds real videos."""
    return "images" if any(f.kind == "images" for f in files) else "videos"


def target_dir(root: Path, f: DeviceFile, kind: str | None = None, date: dt.datetime | None = None) -> Path:
    """`kind`/`date` come from the group, so a Live Photo's .MOV and an .AAE land next to their photo."""
    kind = kind or f.kind
    date = date if date and date != dt.datetime.max else f.date
    if date:
        year, month = f"{date:%Y}", f"{date:%m}"
    elif m := re.match(r"^(\d{4})(\d{2})", f.folder):  # folder names start with YYYYMM
        year, month = m.group(1), m.group(2)
    else:
        year, month = "unknown-date", ""
    return root / kind / year / month if month else root / kind / year


def place(staged: Path, sha256: str, target_folder: Path, name: str) -> tuple[Path, bool]:
    """Finds the final path for a verified staged file.

    Returns (path, already_there):
    - a file with the same name and the same content exists -> (that path, True): moved by an earlier run
    - a file with the same name but different content exists -> try IMG_0410_2.HEIC, _3, ...
    - otherwise -> (free path, False)
    """
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    n = 1
    while True:
        candidate = target_folder / (name if n == 1 else f"{stem}_{n}{dot}{ext}")
        if not candidate.exists():
            return candidate, False
        if candidate.stat().st_size == staged.stat().st_size and hash_file(candidate) == sha256:
            return candidate, True
        n += 1
