# SafeMove

[![Tests](https://github.com/tenotech/SafeMove/actions/workflows/tests.yml/badge.svg)](https://github.com/tenotech/SafeMove/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A small Windows app that **safely moves** photos and videos from your phone to the PC, or straight to an external drive, over the USB cable: oldest first in chunks of a size you choose (e.g. 10 GB), or a whole month, or a single day. Today it supports **iPhone**; Android phones and cameras are on the [roadmap](#roadmap). (Formerly *iPhone Mover*.)

Every file is **copied, verified, and only then deleted from the phone**. If the cable comes out, the phone locks, the drive is unplugged or the app is closed, nothing is lost: whatever is still on the phone hasn't been moved yet, and the next run continues where the last one stopped.

## Highlights

- **Verified moves.** Each file gets a SHA-256 fingerprint while it's copied, then size check, flush to disk, and re-read. Optionally the file is read a second time from the iPhone ("paranoid" mode).
- **Never half a photo.** Live Photos (`.HEIC` + `.MOV`) and edited items are moved as one unit.
- **Resumable.** Interrupted runs leave no partial files, and already-copied files are recognized instead of being copied twice.
- **Tidy archive.** `images\YYYY\MM\` and `videos\YYYY\MM\`, with collision-safe names (`IMG_0001_2.HEIC`).
- **Full record.** `logs\manifest.csv` lists every file moved, with where it went and its fingerprint.
- **External drives.** Move straight to a USB disk: it's found again even under another drive letter, FAT32's 4 GB file limit is checked before starting, and you're reminded to eject it safely.
- **Works with Smart App Control.** It ships only signed programs (the official Python), so it runs on locked-down Windows 11 laptops without an admin install.

## Quick start

1. Download **`SafeMove-portable.zip`** from the [Releases](https://github.com/tenotech/SafeMove/releases) page (or build it: `python build_portable.py`).
2. Right-click the zip → Properties → tick **Unblock**, unzip it, and double-click **`Install.cmd`**.
3. Start **SafeMove** from the Desktop or the Start menu. Plug in the iPhone, unlock it, tap **Trust**, and press **Start**. Begin with **Test mode** checked: it copies but never deletes.

Full instructions: **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**.

## Compatibility

| | Status |
|---|---|
| Windows 11 x64 (Smart App Control on) | ✅ tested |
| Windows 10 x64 | should work (same APIs), not tested yet |
| **iPhone 11 Pro Max**, month folders (`202408__`, `202409_a`…) under `Internal Storage` | ✅ tested (about 25,000 files) |
| Older iOS layout `DCIM\100APPLE` | supported in code, not tested on a device |
| Newer iPhones / iOS versions | **unknown: please help!** |

Newer iPhones or iOS versions may name their photo folders differently. If SafeMove says **"photo folders have names this version doesn't recognize"**, or you have a different model, please run **"SafeMove - device report"** from the Start menu (or `python -m safemove.report`) and [open a device report issue](https://github.com/tenotech/SafeMove/issues/new?template=device_report.yml). The report is read-only and contains no file names, no serial number and no device name.

## Roadmap

- **Android phones** (MTP, like the iPhone): device profiles for `DCIM\Camera`, screenshots, SD cards, dates from file names. Contributions and device reports welcome.
- **Cameras** (PTP/MTP, `DCIM\100XXXXX`).
- **Second copy:** copy to the PC *and* an external drive, verify both, then delete from the phone.

See [ARCHITECTURE.md → Possible improvements](docs/ARCHITECTURE.md#11-possible-improvements) for details.

## Development

Requirements: Windows 10/11 x64, Python 3.11, an iPhone that shows up in Explorer under "This PC". The tests don't need an iPhone.

```powershell
pip install -r requirements-dev.txt
python -m pytest tests                       # 36 tests, using a fake iPhone (no device needed)
python -m safemove.app                   # the window
python -m safemove.cli --chunk-gb 1 --test-mode   # same engine, command line
python -m safemove.cli --month 2024-08 --move     # or --day 2024-08-25
python -m safemove.report                # device report (read-only)
python -m safemove.probe --scan          # read-only scan of the newest month folder
python make_icon.py                          # regenerate safemove\app.ico
python build_portable.py                     # dist\SafeMove-portable.zip (includes a self-test)
```

See **[CONTRIBUTING.md](CONTRIBUTING.md)** before opening a pull request. Deleting from someone's phone is irreversible, so the safety rules there are strict.

## Project layout

```
safemove\
  model.py       device-independent types: DeviceFile, file kinds, folder patterns, DeviceError
  wpd.py         iPhone access through Windows Portable Devices (list, download, delete)
  copier.py      verified copy: hash while writing, size check, fsync, re-read
  grouping.py    Live Photo / edit grouping; plans: oldest N GB, a month, a day
  paths.py       images|videos\YYYY\MM, collision-safe names, "already on PC" detection
  mover.py       the engine: copy → verify → move → delete, per group
  records.py     run logs, manifest.csv, list of edited items
  settings.py    %APPDATA%\SafeMove\settings.json
  drives.py      destination drive: identity (follows letter changes), free-space margin, FAT32 limit
  app.py         tkinter window + background worker thread
  cli.py         command-line runner
  report.py      device report for compatibility issues
  probe.py       low-level device diagnostics (development tool)
  install.py     per-user install / uninstall (shortcuts, Settings > Apps)
tests\           pytest suite with a fake iPhone
build_portable.py, make_icon.py
docs\            user guide, architecture, development log
```

## Documentation

- **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**: install, first run, everyday use, troubleshooting.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: architecture, the move flow, safety model, iPhone quirks found during testing, known limitations.
- **[docs/DEVELOPMENT_LOG.md](docs/DEVELOPMENT_LOG.md)**: the original plan and the record of each phase as it was built and tested.
- **[CHANGELOG.md](CHANGELOG.md)**: what changed in each version.

## Important limitations

- **Edited photos/videos are copied but not deleted.** The iPhone restores them when they're deleted over USB. They're listed in `logs\edited-items-to-delete.txt` so you can delete them in the Photos app.
- After a move, **the PC holds the only copy.** Back up the archive (e.g. to an external drive).
- Windows only, iPhone only, one iPhone at a time.

See [docs/ARCHITECTURE.md → Limitations](docs/ARCHITECTURE.md#9-limitations-and-known-issues) for the full list.

## License and disclaimer

[MIT](LICENSE) © tenotech. SafeMove is not affiliated with or endorsed by Apple. iPhone is a trademark of Apple Inc. The software is provided "as is", without warranty: keep a backup of your photos.
