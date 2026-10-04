"""iPhone access through Windows Portable Devices (WPD), the same route Explorer uses.

Only `delete()` modifies the phone. Everything else is read-only.
"""

from __future__ import annotations

import ctypes
import datetime as dt
import re
from collections import Counter
from collections.abc import Callable, Iterator
from typing import BinaryIO

import comtypes
import comtypes.client

comtypes.client.GetModule("portabledeviceapi.dll")
comtypes.client.GetModule("portabledevicetypes.dll")
from comtypes.gen import PortableDeviceApiLib as port  # noqa: E402
from comtypes.gen import PortableDeviceTypesLib as types  # noqa: E402

_ole32 = ctypes.windll.ole32
_ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


def _key(fmtid: str, pid: int):
    k = port._tagpropertykey()
    k.fmtid = comtypes.GUID(fmtid)
    k.pid = pid
    return k


_OBJ = "{EF6B490D-5CD8-437A-AFFC-DA8B60EE4A3C}"  # WPD_OBJECT_PROPERTIES_V1
KEY_NAME = _key(_OBJ, 4)
KEY_CONTENT_TYPE = _key(_OBJ, 7)
KEY_SIZE = _key(_OBJ, 11)
KEY_ORIGINAL_FILE_NAME = _key(_OBJ, 12)
KEY_DATE_CREATED = _key(_OBJ, 18)
KEY_DATE_MODIFIED = _key(_OBJ, 19)
KEY_DATE_AUTHORED = _key(_OBJ, 20)
KEY_RESOURCE_DEFAULT = _key("{E81E79BE-34F0-41BF-B53F-F1A06AE87842}", 0)

TYPE_FOLDER = comtypes.GUID("{27E2E392-A111-48E0-AB0C-E17705A05F85}")
TYPE_FUNCTIONAL_OBJECT = comtypes.GUID("{99ED0160-17FF-4C44-9D98-1D7A6F941921}")

_VT_DATE = 7
_VT_LPWSTR = 31
_OLE_EPOCH = dt.datetime(1899, 12, 30)

from .model import (  # noqa: E402  (also re-exported: older code imports these from wpd)
    IMAGE_EXTENSIONS, SIDECAR_EXTENSIONS, VIDEO_EXTENSIONS, DeviceError, DeviceFile, media_kind,
)
from .model import PHOTO_FOLDER as _PHOTO_FOLDER  # noqa: E402


def _list_device_ids() -> list[str]:
    mgr = comtypes.client.CreateObject(port.PortableDeviceManager, interface=port.IPortableDeviceManager)
    count = ctypes.c_ulong(0)
    mgr.GetDevices(ctypes.POINTER(ctypes.c_wchar_p)(), ctypes.pointer(count))
    if count.value == 0:
        return []
    ids = (ctypes.c_wchar_p * count.value)()
    mgr.GetDevices(ctypes.cast(ids, ctypes.POINTER(ctypes.c_wchar_p)), ctypes.pointer(count))
    return [i for i in ids[: count.value] if i]


def _is_apple(device_id: str) -> bool:
    return "vid_05ac" in device_id.lower()  # Apple's USB vendor id


UNKNOWN_LAYOUT_MESSAGE = (
    "The iPhone is connected, but its photo folders have names this version doesn't recognize "
    "(maybe a newer iPhone or iOS). Nothing was changed. Please create a device report "
    "(Start menu: \"SafeMove - device report\", or: python -m safemove.report) and open an issue on GitHub "
    "so support can be added.")


class UnknownLayoutError(DeviceError):
    """The phone answers, but no known photo folder layout was found."""


class IPhone:
    """An open connection to an iPhone. Use `IPhone.connect()`."""

    def __init__(self, device_id: str, device, require_photos: bool = True):
        self.device_id = device_id
        self._device = device
        self._content = device.Content()
        self._properties = self._content.Properties()
        self.storage_id, storage_name = self._find_photo_root() or ("", "")
        self.name = f"Apple iPhone ({storage_name})"
        if require_photos and not self.storage_id:
            if self._sees_any_folder():
                raise UnknownLayoutError(UNKNOWN_LAYOUT_MESSAGE)
            raise DeviceError("No photo folders visible on the iPhone.")

    # ---- connection -------------------------------------------------------

    @classmethod
    def connect(cls) -> IPhone:
        """Opens the first connected iPhone that exposes its photos. Raises DeviceError otherwise."""
        try:
            ids = _list_device_ids()
        except comtypes.COMError as e:
            raise DeviceError(f"Could not list portable devices: {e}") from e
        apple = [i for i in ids if _is_apple(i)]
        if not apple:
            raise DeviceError("No iPhone found. Connect it with the cable and unlock it.")

        last_error = ""
        for device_id in apple:
            device = comtypes.client.CreateObject(port.PortableDevice, interface=port.IPortableDevice)
            try:
                client_info = comtypes.client.CreateObject(
                    types.PortableDeviceValues, interface=port.IPortableDeviceValues)
                device.Open(device_id, client_info)
                return cls(device_id, device)
            except UnknownLayoutError:
                device.Close()
                raise
            except (comtypes.COMError, DeviceError) as e:
                last_error = f" ({e})"
                try:
                    device.Close()
                except comtypes.COMError:
                    pass
        raise DeviceError(
            "iPhone found but its photos are not accessible. Unlock the iPhone and tap "
            "\"Trust\"/\"Allow\", then try again." + last_error)

    def close(self) -> None:
        try:
            self._device.Close()
        except comtypes.COMError:
            pass

    def __enter__(self) -> IPhone:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- low-level helpers ------------------------------------------------

    def _children(self, parent_id: str) -> Iterator[str]:
        enum = self._content.EnumObjects(0, parent_id, None)
        next_raw = enum._IEnumPortableDeviceObjectIDs__com_Next
        batch = 200
        while True:
            ids = (ctypes.c_void_p * batch)()
            fetched = ctypes.c_ulong(0)
            next_raw(batch, ctypes.cast(ids, ctypes.POINTER(ctypes.c_wchar_p)), ctypes.byref(fetched))
            for i in range(fetched.value):
                yield ctypes.wstring_at(ids[i])
                _ole32.CoTaskMemFree(ids[i])
            if fetched.value < batch:
                return

    def _values(self, object_id: str, *keys):
        coll = comtypes.client.CreateObject(
            types.PortableDeviceKeyCollection, interface=port.IPortableDeviceKeyCollection)
        for k in keys:
            coll.Add(k)
        return self._properties.GetValues(object_id, coll)

    @staticmethod
    def _str(values, key) -> str | None:
        try:
            return values.GetStringValue(key)
        except comtypes.COMError:
            return None

    @staticmethod
    def _date(values, key) -> dt.datetime | None:
        try:
            pv = values.GetValue(key)
        except comtypes.COMError:
            return None
        if pv.vt != _VT_DATE:
            return None
        union = getattr(pv, pv._fields_[-1][0])
        return _OLE_EPOCH + dt.timedelta(days=union.date)

    def _is_container(self, values) -> bool:
        try:
            t = values.GetGuidValue(KEY_CONTENT_TYPE)
        except comtypes.COMError:
            return False
        return t in (TYPE_FOLDER, TYPE_FUNCTIONAL_OBJECT)

    def _name(self, object_id: str) -> str:
        """iPhone puts names in ORIGINAL_FILE_NAME (NAME is empty); storages use NAME."""
        v = self._values(object_id, KEY_ORIGINAL_FILE_NAME, KEY_NAME)
        return self._str(v, KEY_ORIGINAL_FILE_NAME) or self._str(v, KEY_NAME) or ""

    def _working_storages(self) -> list[tuple[str, str, list[tuple[str, str]]]]:
        """(storage id, name, [(child id, child name)]) for each storage that answers.
        The iPhone also lists placeholder storages that reject every request; they are skipped."""
        result = []
        for storage_id in self._children("DEVICE"):
            try:
                name = self._name(storage_id) or storage_id
                children = [(c, self._name(c)) for c in self._children(storage_id)]
            except comtypes.COMError:
                continue
            result.append((storage_id, name, children))
        return result

    def _sees_any_folder(self) -> bool:
        try:
            return any(children for _, _, children in self._working_storages())
        except comtypes.COMError:
            return False

    def device_info(self) -> dict[str, str]:
        """Model / iOS version as reported over USB. Serial number and device name are left out on purpose."""
        dev = "{26D4979A-E643-4626-9E2B-736DC0C92FDC}"  # WPD_DEVICE_PROPERTIES_V1
        keys = {"manufacturer": _key(dev, 7), "model": _key(dev, 8), "firmware (iOS)": _key(dev, 3),
                "protocol": _key(dev, 6)}
        try:
            v = self._values("DEVICE", *keys.values())
        except comtypes.COMError:
            return {}
        return {label: self._str(v, k) or "?" for label, k in keys.items()}

    def _find_photo_root(self) -> tuple[str, str] | None:
        """Returns (object id, name) of the folder whose sub-folders hold the photos."""
        for storage_id, storage_name, children in self._working_storages():
            for child, name in children:
                if name.upper() == "DCIM":
                    return child, f"{storage_name}\\DCIM"
            if any(_PHOTO_FOLDER.match(n) for _, n in children):
                return storage_id, storage_name
        return None

    # ---- public API -------------------------------------------------------

    _FILE_KEYS = (KEY_ORIGINAL_FILE_NAME, KEY_NAME, KEY_CONTENT_TYPE, KEY_SIZE,
                  KEY_DATE_CREATED, KEY_DATE_AUTHORED, KEY_DATE_MODIFIED)

    def _file_from_values(self, v, object_id: str, folder_name: str) -> DeviceFile | None:
        if self._is_container(v):
            return None
        try:
            size = v.GetUnsignedLargeIntegerValue(KEY_SIZE)
        except comtypes.COMError:
            size = -1  # unknown; such files never pass the size check, so are never deleted
        return DeviceFile(
            object_id=object_id,
            name=self._str(v, KEY_ORIGINAL_FILE_NAME) or self._str(v, KEY_NAME) or object_id,
            folder=folder_name,
            size=size,
            created=self._date(v, KEY_DATE_CREATED),
            authored=self._date(v, KEY_DATE_AUTHORED),
            modified=self._date(v, KEY_DATE_MODIFIED),
        )

    def photo_folders(self) -> dict[str, str]:
        """object id -> name of each photo folder, oldest first.
        Folder names start with YYYYMM (or are numbered 100APPLE, 101APPLE...), so name order is age order."""
        names = {fid: self._name(fid) for fid in self._children(self.storage_id)}
        return dict(sorted(((fid, n) for fid, n in names.items() if _PHOTO_FOLDER.match(n)), key=lambda x: x[1]))

    def list_files(self, on_progress: Callable[[int], None] | None = None,
                   folders: dict[str, str] | None = None) -> list[DeviceFile]:
        """Lists the photos/videos in `folders` (default: all photo folders). Read-only.
        A full scan is slow (~30 min for 25,000 files), so callers should pass only the folders they need.
        Sidecars (.AAE) are included; other files are left out and counted in `self.skipped`."""
        self.skipped: Counter[str] = Counter()
        try:
            return self._list_files_one_by_one(folders if folders is not None else self.photo_folders(), on_progress)
        except comtypes.COMError as e:
            raise DeviceError(f"iPhone stopped responding while listing files: {e}") from e

    def _list_files_one_by_one(self, folders: dict[str, str], on_progress) -> list[DeviceFile]:
        """One request per file. Fast once the phone has prepared its file details
        (~20,000 files in 40 s); the very first listing after connecting can be much slower."""
        files: list[DeviceFile] = []
        for folder_id, folder_name in folders.items():
            for obj_id in self._children(folder_id):
                f = self._file_from_values(self._values(obj_id, *self._FILE_KEYS), obj_id, folder_name)
                if f is None:
                    continue
                if f.kind is None:
                    self.skipped[f.name[f.name.rfind("."):].upper() if "." in f.name else "(none)"] += 1
                    continue
                files.append(f)
            if on_progress:
                on_progress(len(files))
        return files

    def download(self, file: DeviceFile, out: BinaryIO, on_bytes: Callable[[int], None] | None = None,
                 chunk_size: int = 1 << 20) -> None:
        """Streams the file's bytes into `out`. Read-only on the phone."""
        try:
            resources = self._content.Transfer()
            _, stream = resources.GetStream(file.object_id, KEY_RESOURCE_DEFAULT, 0, 0)  # 0 = STGM_READ
            while True:
                buf, n = stream.RemoteRead(chunk_size)
                if n == 0:
                    break
                out.write(ctypes.string_at(buf, n))
                if on_bytes:
                    on_bytes(n)
        except comtypes.COMError as e:
            raise DeviceError(f"iPhone stopped responding while reading {file.name}: {e}") from e

    def delete(self, file: DeviceFile) -> None:
        """Permanently deletes one file from the iPhone. The ONLY method that modifies the phone."""
        if file.kind is None:
            raise DeviceError(f"Refusing to delete {file.name}: only photos, videos and their .AAE edit files may be deleted.")
        # Object ids can be reassigned after a reconnect: make sure the id still points to the same file.
        try:
            v = self._values(file.object_id, KEY_ORIGINAL_FILE_NAME, KEY_SIZE)
            name, size = self._str(v, KEY_ORIGINAL_FILE_NAME), v.GetUnsignedLargeIntegerValue(KEY_SIZE)
        except comtypes.COMError as e:
            raise DeviceError(f"Refusing to delete {file.name}: could not re-check it on the iPhone ({e})") from e
        if name != file.name or size != file.size:
            raise DeviceError(f"Refusing to delete {file.name}: the iPhone now reports {name} ({size:,} bytes)")
        coll = comtypes.client.CreateObject(
            types.PortableDevicePropVariantCollection, interface=port.IPortableDevicePropVariantCollection)
        pv = port.tag_inner_PROPVARIANT()
        pv.vt = _VT_LPWSTR
        object_id = ctypes.c_wchar_p(file.object_id)  # kept alive for the duration of the call
        setattr(getattr(pv, pv._fields_[-1][0]), "pwszVal", object_id.value)
        coll.Add(pv)
        try:
            hr = self._content._IPortableDeviceContent__com_Delete(0, coll, None)  # 0 = no recursion
        except comtypes.COMError as e:
            raise DeviceError(f"Could not delete {file.name} from the iPhone: {e}") from e
        # S_FALSE (1) means "some objects were not deleted" and does not raise: check it explicitly.
        if hr != 0:
            raise DeviceError(f"The iPhone did not delete {file.name} (code {hr}).")
        # And never trust the answer alone: the object must really be gone.
        # (Seen once: the iPhone stalled ~19 s on a delete, reported success, kept the file, then disconnected.)
        try:
            self._values(file.object_id, KEY_ORIGINAL_FILE_NAME, KEY_SIZE).GetUnsignedLargeIntegerValue(KEY_SIZE)
        except comtypes.COMError:
            # Either the file is gone, or the whole iPhone stopped answering: tell them apart.
            try:
                self._name(self.storage_id)
            except comtypes.COMError as e:
                raise DeviceError(f"iPhone stopped responding; could not confirm {file.name} was deleted.") from e
            return  # iPhone answers, file doesn't exist any more: deleted
        raise DeviceError(f"The iPhone still lists {file.name} after deleting it.")
