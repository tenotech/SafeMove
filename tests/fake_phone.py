"""An in-memory iPhone for tests: same methods as wpd.IPhone, plus failure injection."""

from __future__ import annotations

import datetime as dt

from safemove.model import DeviceError, DeviceFile


class FakePhone:
    def __init__(self):
        self.content: dict[str, bytes] = {}  # object id -> bytes
        self.files: dict[str, DeviceFile] = {}  # object id -> file
        self.deleted: list[str] = []  # names, in deletion order
        self.disconnect_on: str | None = None  # name whose download dies halfway
        self.truncate: set[str] = set()  # names whose download is silently short
        self.fail_delete: set[str] = set()
        self.listed_folders: list[str] = []

    def add(self, folder: str, name: str, data: bytes, when: dt.datetime) -> DeviceFile:
        oid = f"o{len(self.content) + 1}"
        f = DeviceFile(oid, name, folder, len(data), when, None, when)
        self.content[oid], self.files[oid] = data, f
        return f

    # ---- IPhone API ----

    def photo_folders(self) -> dict[str, str]:
        names = sorted({f.folder for f in self.files.values()})
        return {f"F{n}": n for n in names}

    def list_files(self, on_progress=None, folders=None) -> list[DeviceFile]:
        wanted = set((folders or self.photo_folders()).values())
        self.listed_folders += sorted(wanted)
        return [f for f in self.files.values() if f.folder in wanted and f.kind]

    def download(self, file: DeviceFile, out, on_bytes=None, chunk_size: int = 4) -> None:
        if file.object_id not in self.content:
            raise DeviceError(f"{file.name} no longer exists")
        data = self.content[file.object_id]
        if file.name in self.truncate:
            data = data[:-1]
        for i in range(0, len(data), chunk_size):
            if file.name == self.disconnect_on and i >= len(data) // 2:
                raise DeviceError("device disconnected")
            out.write(data[i:i + chunk_size])
            if on_bytes:
                on_bytes(len(data[i:i + chunk_size]))

    def delete(self, file: DeviceFile) -> None:
        if file.name in self.fail_delete:
            raise DeviceError("delete refused")
        del self.content[file.object_id]
        del self.files[file.object_id]
        self.deleted.append(file.name)

    def names(self) -> set[str]:
        return {f.name for f in self.files.values()}
