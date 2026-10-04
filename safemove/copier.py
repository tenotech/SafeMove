"""Copy one iPhone file to disk and prove the local copy is complete and intact.

hash while writing -> size check -> flush to disk (fsync) -> re-read and re-hash.
On any failure the partial local file is removed.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from typing import TYPE_CHECKING

from .model import DeviceError, DeviceFile

if TYPE_CHECKING:
    from .wpd import IPhone

_CHUNK = 1 << 20


@dataclass(frozen=True)
class CopyResult:
    ok: bool
    sha256: str = ""
    bytes_written: int = 0
    error: str = ""
    error_kind: str = ""  # "device" (phone gone), "disk" (local write problem) or "verify" (data mismatch)


class _HashingWriter:
    """File-like object that hashes and counts bytes as they are written."""

    def __init__(self, f):
        self._f = f
        self.hash = hashlib.sha256()
        self.written = 0

    def write(self, data: bytes) -> int:
        self.hash.update(data)
        self._f.write(data)
        self.written += len(data)
        return len(data)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def verified_copy(phone: IPhone, file: DeviceFile, dest: Path,
                  on_bytes: Callable[[int], None] | None = None) -> CopyResult:
    """Copies `file` to `dest` (which must not exist). Read-only on the phone."""
    try:
        with open(dest, "xb") as f:
            writer = _HashingWriter(f)
            phone.download(file, writer, on_bytes)
            f.flush()
            os.fsync(f.fileno())
        written_hash = writer.hash.hexdigest()
    except DeviceError as e:
        _remove(dest)  # never leave a partial file behind
        return CopyResult(False, error=str(e), error_kind="device")
    except OSError as e:
        _remove(dest)
        return CopyResult(False, error=f"could not write {dest}: {e}", error_kind="disk")

    if file.size < 0 or writer.written != file.size:
        _remove(dest)
        return CopyResult(False, written_hash, writer.written,
                          f"size mismatch: iPhone says {file.size:,} bytes, received {writer.written:,}", "verify")

    if hash_file(dest) != written_hash:
        _remove(dest)
        return CopyResult(False, written_hash, writer.written,
                          "file on disk does not match what was received (disk write error)", "verify")

    return CopyResult(True, written_hash, writer.written)


def hash_on_phone(phone: IPhone, file: DeviceFile) -> str:
    """Reads the file from the phone a second time, only to hash it (the "paranoid" check)."""
    class _Sink:
        def __init__(self):
            self.hash = hashlib.sha256()

        def write(self, data: bytes) -> int:
            self.hash.update(data)
            return len(data)

    sink = _Sink()
    phone.download(file, sink)
    return sink.hash.hexdigest()
