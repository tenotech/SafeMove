"""User settings, saved to %APPDATA%\\SafeMove\\settings.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

_APPDATA = Path(os.environ.get("APPDATA", Path.home()))
SETTINGS_PATH = _APPDATA / "SafeMove" / "settings.json"
LEGACY_SETTINGS_PATH = _APPDATA / "iPhoneMover" / "settings.json"  # before the rename to SafeMove


@dataclass
class Settings:
    destination: str = r"C:\SafeMove"
    chunk_gb: float = 10.0
    mode: str = "size"  # size (oldest first, up to chunk_gb) | month | day
    month: str = ""  # YYYY-MM
    day: str = ""  # YYYY-MM-DD
    test_mode: bool = True  # copy only, never delete. Off only once the user trusts the app
    paranoid: bool = False  # read each file twice from the phone (slower)
    min_free_gb: float = 20.0  # free space to keep on the Windows (system) drive
    min_free_gb_other: float = 1.0  # free space to keep on any other drive (external disks, USB sticks)
    # The destination's drive, so it can be found again if Windows gives it another letter (E: -> F:)
    dest_volume_serial: int = 0
    dest_volume_label: str = ""

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH, legacy: Path = LEGACY_SETTINGS_PATH) -> Settings:
        for candidate in (path, legacy):
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            known = {f.name for f in fields(cls)}
            try:
                settings = cls(**{k: v for k, v in data.items() if k in known})
            except TypeError:
                continue
            if candidate is legacy:
                settings.save(path)  # carry the old iPhone Mover settings over once
            return settings
        return cls()

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
