"""Device report: how an iPhone exposes its photos over USB, to add support for new models / iOS versions.

    python -m safemove.report          (or "SafeMove - device report" in the Start menu)

Read-only. Contains no file names, no serial number and no device name: folder names are reduced to
patterns (digits -> 9) and files are only counted by extension and name pattern.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import re
import sys
import time
from collections import Counter
from pathlib import Path

from . import __version__
from .model import PHOTO_FOLDER


def _pattern(name: str) -> str:
    return re.sub(r"\d", "9", name)


def _name_pattern(name: str) -> str:
    stem = name.rsplit(".", 1)[0]
    for pat, label in ((r"^IMG_E\d+$", "IMG_E9999 (edited)"), (r"^IMG_O\d+$", "IMG_O9999"),
                       (r"^IMG_\d+$", "IMG_9999"), (r"^[A-Z]{4}\d{4}$", "ABCD9999")):
        if re.match(pat, stem, re.IGNORECASE):
            return label
    return "other"


def build_report() -> str:
    import comtypes
    from .wpd import IPhone, _is_apple, _list_device_ids, port, types

    out = [
        "## SafeMove device report",
        "",
        f"- SafeMove {__version__}, Python {platform.python_version()}, {platform.platform()}",
        f"- Created {dt.datetime.now():%Y-%m-%d %H:%M}",
    ]
    ids = _list_device_ids()
    apple = [i for i in ids if _is_apple(i)]
    out.append(f"- Portable devices: {len(ids)}, Apple devices: {len(apple)}")
    if not apple:
        out.append("\n**No iPhone found.** Connect it, unlock it, tap Trust, check it appears in Explorer > This PC.")
        return "\n".join(out)

    device = comtypes.client.CreateObject(port.PortableDevice, interface=port.IPortableDevice)
    device.Open(apple[0], comtypes.client.CreateObject(types.PortableDeviceValues, interface=port.IPortableDeviceValues))
    phone = IPhone(apple[0], device, require_photos=False)
    try:
        out += ["", "### Device"] + [f"- {k}: {v}" for k, v in phone.device_info().items()]

        out += ["", "### Storages"]
        listed = list(phone._children("DEVICE"))
        working = phone._working_storages()
        out.append(f"- Listed: {len(listed)}, answering: {len(working)}")
        for _, sname, children in working:
            pats = Counter(_pattern(n) for _, n in children)
            out.append(f"- **{sname}**: {len(children)} folders")
            for p, n in pats.most_common(12):
                known = "known" if PHOTO_FOLDER.match(p) or p.upper() == "DCIM" else "UNKNOWN"
                out.append(f"  - `{p}` × {n} ({known})")
            dcim = next((cid for cid, n in children if n.upper() == "DCIM"), None)
            if dcim:
                sub = Counter(_pattern(phone._name(c)) for c in phone._children(dcim))
                out.append("  - inside DCIM: " + ", ".join(f"`{p}` × {n}" for p, n in sub.most_common(12)))

        out += ["", "### Photo folders"]
        if not phone.storage_id:
            out.append("- **No known photo folder layout found.** The folder patterns above show what this "
                       "iPhone uses instead.")
            return "\n".join(out)
        folders = phone.photo_folders()
        out.append(f"- Layout found under: {phone.name}; {len(folders)} photo folders")
        if folders:
            fid, fname = list(folders.items())[-1]
            start = time.time()
            files = phone.list_files(folders={fid: fname})
            secs = time.time() - start
            out.append(f"- Newest folder (`{_pattern(fname)}`): {len(files)} files listed in {secs:.1f} s; "
                       f"not handled (left alone): {sum(phone.skipped.values())} "
                       f"{dict(phone.skipped) if phone.skipped else ''}")
            ext = Counter(Path(f.name).suffix.upper() or "(none)" for f in files)
            out.append("- Extensions: " + ", ".join(f"{e} × {n}" for e, n in ext.most_common()))
            names = Counter(_name_pattern(f.name) for f in files)
            out.append("- Name patterns: " + ", ".join(f"{p} × {n}" for p, n in names.most_common()))
            out.append(f"- With a date: {sum(f.date is not None for f in files)}/{len(files)}, "
                       f"with a size: {sum(f.size >= 0 for f in files)}/{len(files)}")
            mismatch = sum(1 for f in files if f.date and not fname.startswith(f"{f.date:%Y%m}"))
            if re.match(r"^\d{6}", fname):
                out.append(f"- Files whose date month differs from the folder month: {mismatch}")
    finally:
        phone.close()
    out += ["", "_No file names, serial number or device name are included._"]
    return "\n".join(out)


def main() -> None:
    try:
        text = build_report()
    except Exception as e:  # the report must always produce something useful
        text = f"## SafeMove device report\n\nFailed: {e!r}"
    desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    path = (desktop if desktop.is_dir() else Path.cwd()) / "SafeMove-device-report.txt"
    path.write_text(text + "\n", encoding="utf-8")
    if sys.stdout and sys.stdout.isatty():
        print(text)
        print(f"\nSaved to {path}")
    else:  # started from a shortcut (pythonw): show it
        os.startfile(path)


if __name__ == "__main__":
    main()
