# Contributing to SafeMove

Thanks for helping! SafeMove **deletes photos from people's phones**, and that can't be undone. So the bar for anything that touches copying, verification or deletion is high. Everything else (UI, docs, device support, tests) is very welcome and easy to get into.

## Ways to help

| | |
|---|---|
| **Device reports** | The most useful contribution right now. Run "SafeMove - device report" (or `python -m safemove.report`) with your iPhone connected and [open a device report issue](https://github.com/tenotech/SafeMove/issues/new?template=device_report.yml). It's read-only and contains no file names, serial number or device name. |
| **Bug reports** | Use the bug report template. Attach the run log from `<destination>\logs\` if you can. Check it for anything private first: it contains file names. |
| **Code** | Fixes, new device layouts, UI improvements, tests. Please open an issue first for anything bigger than a small fix. |
| **Docs** | Corrections, translations of the user guide, screenshots. |

## Development setup

Windows 10/11 x64 and Python 3.11:

```powershell
git clone <your fork>
cd SafeMove
pip install -r requirements-dev.txt
python -m pytest tests          # must pass; no iPhone needed
python -m safemove.app      # run the app from source
```

Smart App Control: the app runs on the signed Python, so it's fine. Don't add anything that needs a compiled, unsigned `.exe`/`.dll` (see [ARCHITECTURE.md §2](docs/ARCHITECTURE.md#2-technology-choices)).

## How the code is organized

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) first: the components, the move flow and the safety model are all there. In short:

- `model.py`, `grouping.py`, `paths.py`, `copier.py`, `mover.py` and `records.py` are the **engine**. They don't import the Windows device API, so they're fully testable with `tests/fake_phone.py`.
- `wpd.py` is the **only** module that talks to the phone, and `IPhone.delete()` is the **only** function that changes it.
- `app.py` (tkinter), `cli.py`, `report.py` and `install.py` are front-ends.

## Safety rules (non-negotiable)

A pull request that weakens any of these won't be merged:

1. **Never delete before the whole group is verified on disk:** size match, SHA-256 written equals SHA-256 re-read after `fsync`.
2. **Never overwrite** a file in the archive. Same content means "already on PC"; different content means a `_2` name.
3. **Nothing half-written in the archive.** Copy to `.staging\`, then an atomic rename.
4. **Every delete is double-checked** (`S_FALSE` is a failure; the object must be gone afterwards; a phone that stops answering is not "deleted").
5. **Only photos, videos and their `.AAE`** are ever deleted. Edited items are never deleted (the iPhone restores them; see the [development log](docs/DEVELOPMENT_LOG.md)).
6. **Test mode never deletes.**
7. Any change to these paths needs a **test with the fake phone** that reproduces the failure case (disconnect, truncation, refused delete…).

## Adding support for a new folder layout

1. Get a device report (yours or from an issue).
2. Extend `PHOTO_FOLDER` in `safemove/model.py` and, if needed, `_find_photo_root()` in `wpd.py`. Month/day planning reads `YYYYMM` from folder names (`grouping.folder_month`); undated layouts are always fully scanned.
3. Add tests with a `FakePhone` that uses the new folder names.
4. Test on the real device in **Test mode** first, then a small move (1 GB). After a replug, check the iPhone's Photos app and that the deleted files stay deleted.
5. Add the model to the compatibility table in `README.md`.

## Pull requests

- Keep them focused, one topic each.
- `python -m pytest tests` must pass (CI runs it on Windows).
- Match the existing style: type hints, short docstrings that explain *why*, no new dependencies unless really needed. Each new dependency must be pure Python, or signed, so the portable build keeps working with Smart App Control.
- Update the docs (user guide / architecture) and `CHANGELOG.md` when behavior changes.
- If you tested on a real iPhone, say which model, iOS version and what you ran (test mode / move, how much).

## Releases (maintainers)

1. Update `__version__` in `safemove/__init__.py` and `CHANGELOG.md`.
2. `python build_portable.py`. It checks itself; then check that all binaries are signed (see ARCHITECTURE §8).
3. Tag `vX.Y.Z` and attach `dist/SafeMove-portable.zip` to the GitHub release.

## Code of conduct

Be kind and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
