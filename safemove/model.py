"""Device-independent definitions: files on the phone, file types, folder names, errors.

Kept free of Windows device APIs so the engine and its tests run anywhere (including CI).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

# Photo folders. Older iOS: DCIM\100APPLE, 101APPLE... iOS on an iPhone 11 Pro Max (tested): month folders
# like 202408__, 202409_a directly under "Internal Storage". Other layouts: please send a device report
# (python -m safemove.report), see CONTRIBUTING.md.
PHOTO_FOLDER = re.compile(r"^(\d{6}_.*|\d{3}APPLE)$", re.IGNORECASE)

# Only these are ever listed, copied or deleted. Anything else is left alone.
# .AAE files hold the edits made in the Photos app: they travel with their photo/video (same IMG number),
# because the iPhone restores an edited item whose .AAE is left behind. An .AAE without media is never touched.
SIDECAR_EXTENSIONS = frozenset({".aae"})
IMAGE_EXTENSIONS = frozenset({".heic", ".heif", ".jpg", ".jpeg", ".png", ".gif", ".dng", ".tif", ".tiff", ".webp"})
VIDEO_EXTENSIONS = frozenset({".mov", ".mp4", ".m4v", ".3gp", ".avi"})


def media_kind(name: str) -> str | None:
    """'images', 'videos', 'sidecar' (.AAE), or None for anything else."""
    ext = name[name.rfind("."):].lower() if "." in name else ""
    if ext in IMAGE_EXTENSIONS:
        return "images"
    if ext in VIDEO_EXTENSIONS:
        return "videos"
    if ext in SIDECAR_EXTENSIONS:
        return "sidecar"
    return None


@dataclass(frozen=True)
class DeviceFile:
    object_id: str  # device object id, used for download and delete
    name: str  # e.g. IMG_0410.HEIC
    folder: str  # e.g. 202509_a
    size: int
    created: dt.datetime | None
    authored: dt.datetime | None
    modified: dt.datetime | None

    @property
    def date(self) -> dt.datetime | None:
        """Best date the phone gives: created, else authored, else modified."""
        return self.created or self.authored or self.modified

    @property
    def path(self) -> str:
        return f"{self.folder}/{self.name}"

    @property
    def kind(self) -> str | None:
        """'images', 'videos', 'sidecar', or None (never copied or deleted)."""
        return media_kind(self.name)


class DeviceError(Exception):
    """The iPhone is missing, locked, not trusted, or disconnected mid-operation."""
