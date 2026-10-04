"""Run log (readable text, one file per run) and manifest (CSV of every file ever moved, append-only)."""

from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path

EDITED_STATUS = "edited, kept on iPhone"
MANIFEST_COLUMNS = ["moved_at", "source_folder", "source_name", "dest_path", "size_bytes", "sha256", "status"]


class RunLog:
    def __init__(self, logs_dir: Path):
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
        self._f = open(self.path, "a", encoding="utf-8")

    def write(self, text: str) -> None:
        try:
            self._f.write(f"{dt.datetime.now():%H:%M:%S}  {text}\n")
            self._f.flush()
        except (OSError, ValueError):
            pass  # the log lives on the destination drive, which may just have been unplugged

    def close(self) -> None:
        try:
            self._f.close()
        except OSError:
            pass


class Manifest:
    """status: deleted | kept (test mode) | delete failed | edited, kept on iPhone | 'already on PC, ' + ..."""

    def __init__(self, path: Path):
        self.path = path  # the folder is created on first write: the destination drive may not be connected yet

    def add(self, source_folder: str, source_name: str, dest_path: Path, size: int, sha256: str,
            status: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(MANIFEST_COLUMNS)
            w.writerow([f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}", source_folder, source_name, str(dest_path),
                        size, sha256, status])

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def kept_edited(self) -> set[tuple[str, str, int]]:
        """(folder, name, size) of edited files that are safe on the PC and stay on the iPhone on purpose."""
        return {(r["source_folder"], r["source_name"], int(r["size_bytes"]))
                for r in self.rows() if r["status"].endswith(EDITED_STATUS)}

    def write_edited_list(self, path: Path) -> int:
        """Human-readable list of edited items to delete by hand in the Photos app. Returns how many."""
        items: dict[tuple[str, str], list[str]] = {}
        for r in self.rows():
            if r["status"].endswith(EDITED_STATUS):
                items.setdefault((r["source_folder"], _number(r["source_name"])), []).append(r["dest_path"])
        lines = [
            "Edited photos/videos: safe on this PC, but the iPhone does not let them be deleted over USB.",
            "Delete them yourself in the iPhone Photos app (they are listed by month folder and number),",
            "then empty Albums > Recently Deleted.",
            "",
        ]
        for (folder, number), paths in sorted(items.items()):
            month = Path(paths[0]).parent  # ...\videos\2024\08
            lines.append(f"{month.parent.name}-{month.name}  IMG_{number}  (iPhone folder {folder})  ->  "
                         + "  |  ".join(sorted(set(paths))))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return len(items)


def _number(name: str) -> str:
    m = re.match(r"^IMG_[EO]?(\d+)", name, re.IGNORECASE)
    return m.group(1) if m else name.rsplit(".", 1)[0]
