# Changelog

All notable changes to this project. Versions follow [semantic versioning](https://semver.org/).

## [1.2.0] - unreleased

### Changed
- **Renamed to SafeMove** (was *iPhone Mover*): package `safemove`, `%APPDATA%\SafeMove`, `%LOCALAPPDATA%\Programs\SafeMove`, `SafeMove-portable.zip`. Installing SafeMove removes the old iPhone Mover shortcuts, Apps entry and program folder; the old settings (including the destination) are taken over automatically. Photos and logs are untouched.

### Added
- **External drives as destination:**
  - the drive is remembered by its volume serial number and followed to a new letter (E: → F:);
  - the destination line shows the drive, its file system and free space, and turns red when it's unplugged (checked every 3 s);
  - free-space margin of 1 GB on drives other than the Windows drive (20 GB there); the CLI's `--min-free-gb` defaults to the same rule;
  - FAT32 drives: a selection containing a file of 4 GB or more is refused before anything is copied;
  - a clear message when the drive is unplugged during a run, and a "Safely Remove Hardware" reminder at the end.
- **Device report** (`python -m safemove.report`, Start menu "SafeMove - device report", `Device report.cmd` in the zip): describes how a connected iPhone exposes its photos (model, iOS version, folder patterns, file types) without file names, serial number or device name. Used to add support for new iPhones / iOS versions.
- A clear message when the iPhone's photo folders use an unknown layout, instead of "not accessible".
- Open-source files: MIT license, contributing guide, code of conduct, issue and pull request templates, GitHub Actions test workflow.

### Changed
- `DeviceFile`, file kinds and folder patterns moved to `safemove/model.py`. The engine and the tests no longer need the Windows device API (they still work as before; `wpd` re-exports the names).
- The build log `PLAN.md` became `docs/DEVELOPMENT_LOG.md` (file names and library figures anonymized).

## [1.1.0] - 2026-10-04

### Added
- Choose what to move: **oldest first up to N GB**, a **whole month**, or **one day** (window and `--month` / `--day` on the command line). The month list comes from folder names (instant); the day list shows files and size per day.
- Documentation: README, user guide, architecture, `.gitignore`.

## [1.0.0] - 2026-10-04

First version.
- Verified move: SHA-256 while copying, size check, fsync, re-read; optional second read from the iPhone.
- Groups: Live Photos and edited items move together; edited items are copied but kept on the iPhone.
- Resumable: staging folder, atomic rename, "already on PC" recognition, collision-safe names.
- Deletes double-checked on the device.
- tkinter window with progress, Stop safely, disconnect banner, test mode; command-line runner.
- Portable zip with only signed binaries (works with Smart App Control) and per-user installer (shortcuts, Settings > Apps, uninstall).
