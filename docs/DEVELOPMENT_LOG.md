# Development log

The original plan of SafeMove and the record of each phase as it was built and tested (October 2026, iPhone 11 Pro Max, Windows 11 with Smart App Control on). The app was called *iPhone Mover* during most of this log; names and paths below use the current name. File names and library figures are anonymized.

---

A small Windows app that **moves** photos and videos from an iPhone (USB cable) to the laptop, in chunks of N GB, oldest first. Each file is deleted from the iPhone **only after** its copy on the laptop has been verified.

**Why:** copying and pasting in Explorer gets interrupted, and afterwards there's no way to know which files were copied and which can be deleted. With this app the iPhone itself becomes the progress tracker. Anything still on the phone hasn't been moved yet; anything gone from the phone is safely on the laptop.

---

## 1. Decisions

| Topic | Decision |
|---|---|
| Platform | Windows 11, iPhone over USB, no iCloud Photos (the iPhone holds the only copy) |
| Technology | **Python 3.11** + tkinter UI. (C#/.NET was tried first, but Windows Smart App Control blocks every unsigned program we build. Python is signed, so it isn't blocked) |
| iPhone access | Windows Portable Devices (WPD), the same route Explorer uses, through `comtypes` (talks directly to the Windows WPD interface). Deleting this way lets iOS update its Photos library properly |
| Destination | `C:\SafeMove` (changeable in the UI) |
| Folders | `images\YYYY\MM\`, `videos\YYYY\MM\`, `logs\`, `.staging\` |
| Order | Oldest first |
| Chunk size | 10 GB by default, changeable for each run |
| Free-space margin | Never let the destination drive go below **20 GB free** |
| Deletion | Automatic, file by file, after verification. Disabled in **Test mode** |
| What is moved | **Photos and videos only** (see File types). An `.AAE` edit file is copied together with its photo/video; any other file is never copied and never deleted |
| Edited items | Copied and verified, but **not deleted** (the iPhone restores them). Listed in `logs\edited-items-to-delete.txt` for manual deletion in the Photos app |
| Portability | Must run on **any Windows laptop**, including ones with Smart App Control on: a portable zip with only signed programs, no install (see Phase 5) |

---

## 2. How one run works

```
1. Detect the iPhone (it must be unlocked, with "Trust This Computer" accepted)
2. Scan month folders oldest first (`202408__`, `202409__`, …), stopping once the scanned size reaches the chunk size (plus one more folder, so groups that span folders aren't cut). A full scan takes ~30 min; this takes seconds
3. Group related files (Live Photos, edits); sort the groups oldest first
4. Pick groups until the total reaches the chunk size (a group is never split)
5. Check free space: (free − chunk size) must be ≥ 20 GB, otherwise Start is blocked
6. For each group:
     for each file in the group:
        a. stream it from the iPhone into .staging\, computing SHA-256 on the way
        b. check bytes written == size reported by the iPhone
        c. flush to disk, re-read the staged file, check its SHA-256 matches
        d. move it (rename) to images|videos\YYYY\MM\<name>
        e. write a line to the manifest
     if EVERY file in the group is verified → delete the group's files from the iPhone
     otherwise → delete nothing from this group, log the error
7. Show the summary and save the log
```

### File groups
iPhone files that belong together share a number: `IMG_0410.HEIC`, `IMG_0410.MOV` (the Live Photo video), `IMG_E0410.HEIC` (an edited version), `IMG_0410.AAE` (the edit instructions).
- **Group key** = folder + number (`100APPLE/0410`).
- A group is moved and deleted **as a unit**. This keeps a Live Photo from being half-deleted.
- **Group date** = the oldest date among its files.

### File types
- **images:** `.heic .heif .jpg .jpeg .png .gif .dng .tif .tiff .webp`
- **videos:** `.mov .mp4 .m4v .3gp .avi`
- **anything else** (mainly `.aae`): ignored. Not listed, not copied, not deleted. `delete()` refuses non-media files as a second safety net

### Dates
The date of each file comes from the iPhone (WPD "date created", falling back to "date modified"). It's used for sorting and for the `YYYY\MM` folder. Reading the date stored inside the photo (EXIF) is left for later (see §9).

### Name collisions
Numbering on the iPhone restarts after `IMG_9999`, so two different photos can have the same name.
- The destination already has a file with that name and **the same SHA-256** → the photo was already moved in an earlier interrupted run. The staged copy is discarded, and the file counts as verified, so it can be deleted from the iPhone.
- The destination has a file with that name but **a different SHA-256** → it's saved under a new name, `IMG_0410_2.HEIC` (then `_3`, …).

---

## 3. Verification: what it guarantees

| Check | Catches |
|---|---|
| Bytes copied == size reported by the iPhone | Interrupted or truncated transfers (the main real risk) |
| Hash while copying == hash of the file re-read from disk | Write or disk errors on the laptop |
| `Flush(true)` before re-reading | Data still sitting in the Windows cache, which could be lost in a crash or power loss |
| Atomic rename from staging to final folder | Half-written files never show up in the archive |

USB has its own built-in error checking, so silent corruption between the iPhone and the PC is very unlikely.

**Optional "Paranoid" setting, off by default:** read each file from the iPhone a second time and compare hashes before deleting. It's a true end-to-end check, but it doubles the transfer time.

---

## 4. Interruptions and errors

| Situation | Behavior |
|---|---|
| **Stop safely** pressed | Finishes the current group, then stops |
| iPhone disconnected or locked mid-file | Deletes the partial staged file, deletes nothing from the iPhone, shows a red banner: *"iPhone disconnected — nothing lost. Reconnect, unlock, and press Start to continue."* |
| App crash or PC shutdown | Next start: `.staging\` is emptied (leftovers are incomplete by definition). Already-moved files are recognized by the name + hash check |
| Disk full or write error | Stop the run, delete nothing for the current group, show an error |
| Delete on iPhone fails | Log a warning. The file stays on the phone and is recognized as already moved on the next run |
| A file fails verification | Delete nothing from its group, log it, move on to the next group. Listed in the summary |

**Nothing is deleted from the iPhone unless the code path reached "group fully verified."**

---

## 5. UI (one window)

```
┌─ SafeMove ────────────────────────────────────────┐
│ 📱 iPhone: Connected (Apple iPhone)       [Rescan] │
│    1,847 files · 128.4 GB on phone · oldest: 2021-03 │
│                                                       │
│ Destination: C:\SafeMove                    [Browse]   │
│ Drive C: free space: 212.5 GB  ✓                     │
│                                                       │
│ Move this time: [ 10 ] GB   (oldest first)           │
│   → 312 files, 2021-03-02 → 2021-07-18               │
│ ☐ Test mode (copy only, don't delete from iPhone)    │
│ ☐ Paranoid verify (slower)                           │
│                                                       │
│        [ Start ]   [ Stop safely ]   [Open folder]   │
│                                                       │
│ ███████████░░░░░░░░  4.1 / 10 GB   (128 / 312 files) │
│ Current: IMG_0412.MOV  (820 MB)  · 38 MB/s · ~2 min  │
│                                                       │
│ ┌ Log ─────────────────────────────────────────────┐ │
│ │ ✓ IMG_0410.HEIC  copied, verified, deleted       │ │
│ │ ⚠ ...                                            │ │
│ └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

- **Status line:** shows not connected, locked/not trusted, connected or scanning, each with a hint on what to do.
- **Chunk preview** updates live when the size changes: number of files and the date range.
- **Free-space indicator:** green; orange under 50 GB; red (and Start blocked) when the chunk would breach the 20 GB margin.
- **Start** is disabled when there's no device, the destination is invalid or there isn't enough space.
- **Log list** is color-coded: green ✓, orange ⚠, red ✗.
- **End-of-run summary popup:** files moved, GB moved, errors, time taken, what's left on the phone.
- **Settings** (destination, chunk size, test mode, paranoid) are saved to `%AppData%\SafeMove\settings.json`.

The work runs on a background thread. The UI receives progress updates and stays responsive. Stopping uses a cancellation signal that is checked between files and between groups.

---

## 6. Logs and records

- `C:\SafeMove\logs\2026-10-03_14-22-05.txt`: a readable log of one run.
- `C:\SafeMove\logs\manifest.csv`: one line per moved file, never overwritten, only appended to:
  `moved_at, source_path, dest_path, size_bytes, sha256, deleted_from_iphone`

  This is your permanent record of what was moved, where it went and its fingerprint.

---

## 7. Project structure

```
SafeMove\
  PLAN.md                    (this file, now docs\DEVELOPMENT_LOG.md)
  requirements.txt           ← comtypes
  run-probe.cmd              ← double-click to run the Phase 1 probe
  safemove\
    wpd.py                   ← iPhone access (list, download, delete). delete() is the only call that modifies the phone
    copier.py                ← copy + SHA-256 + size check + fsync + re-read
    probe.py                 ← Phase 1 console probe
    grouping.py              ← groups by folder + number           (Phase 2)
    planner.py               ← picks groups oldest first up to N GB (Phase 2)
    paths.py                 ← images/videos, YYYY\MM, collision naming (Phase 2)
    mover.py                 ← copy → verify → move → delete; progress and cancel (Phase 2)
    log.py / settings.py     (Phase 2)
    app.py                   ← tkinter window (Phase 3)
  tests\                     ← pytest with a fake phone
```

A fake phone in the tests lets all the safety logic be tested, including simulated disconnects mid-file, without touching the real iPhone.

---

## 8. Build phases

### Phase 0: Setup
- [x] Python 3.11 (already installed) + `comtypes` 1.4.17 (`pip install -r requirements.txt`)
- [x] (.NET 8 SDK also installed, but no longer used because of Smart App Control. It can be uninstalled from Windows Settings → Apps)

### Phase 1: Proof of concept (gate: nothing goes further until it passes)
- [x] Detect the iPhone. It shows 3 storages; only the 3rd (`Internal Storage`) is real, the other 2 reject every request
- [x] Photo folders are month folders (`202509_a` …) directly under `Internal Storage`, not `DCIM`. 70 folders, about 26,000 files
- [x] Names are in the "original file name" property; created and modified dates are available
- [x] Full listing (2026-10-03): **about 25,000 photos/videos, about 175 GB** (~15,500 images, ~9,800 videos; MOV = ~133 GB), plus ~930 `.AAE` ignored. Dates from 2024-08-18 to 2026-10-03; every file has a date, and the dates match the month folders, so they are real capture dates
- [x] A full scan takes **~29 min**, while one month folder takes under 1 s. So the app scans the **oldest folders only, until the chunk is full**, and never does a full scan at startup
- [ ] Compare with the Photos app counts (Live Photos count as 1 item there but are 2 files here)
- [x] Copy 1 file and confirm it opens correctly on the PC
- [x] **First real copy → verify → delete (2026-10-03), Live Photo `202408__/IMG_1001` (.HEIC + .MOV):** both copied and verified (size, SHA-256, re-read from disk), both read a second time from the iPhone with matching SHA-256, then both deleted through WPD. A rescan showed N → N-2 files, with exactly those 2 removed. The copies are originals (HEIC/QuickTime headers, not converted). Kept in `C:\SafeMove\_probe\delete-test\`
- [x] `delete()` re-checks the file's name and size on the iPhone right before deleting, and refuses non-media files
- [x] **Deletion test:** done on the real Live Photo above instead of throwaway photos. Checked on the iPhone: removed cleanly, no grey thumbnails, the nearby Live Photos are fine. ✅ **Phase 1 passed**
- ~~Original deletion test plan:~~ take 3 throwaway photos (one of them a Live Photo) and delete them through the app. On the iPhone, check:
  - they vanish from Photos cleanly (no grey thumbnails)
  - whether they appear in "Recently Deleted" (assume they don't, so deletion is permanent)
  - the Live Photo is fully gone

### Phase 2: Core engine (test mode only, no deleting)
- [x] `grouping.py` (groups + oldest-first chunk, scanning only the folders needed), `paths.py` (images/videos, YYYY\MM, `_2` collision names), `records.py` (run log + manifest.csv), `settings.py`
- [x] `mover.py`: streaming copy + SHA-256, size check, fsync, re-read and verify, atomic move from `.staging`, manifest, per-group delete, Stop safely, error handling (disconnect / disk / verification)
- [x] Clean up `.staging\` at startup; recognize files that were already moved (same name and same SHA-256 means "already on PC")
- [x] **A group containing a photo goes entirely to `images\`**: Live Photo `.MOV` clips stay next to their photo, and `videos\` holds only real videos (decided after the first real run)
- [x] 17 automated tests with a fake iPhone (`python -m pytest tests`), all passing: disconnect mid-file, rerun after interruption, name collision, truncated file, delete failure, low disk space, Stop safely, test mode, `.AAE` untouched
- [x] `cli.py` command-line runner: `python -m safemove.cli --chunk-gb 1 --test-mode` (or `--move`)
- [x] Real iPhone, **test mode, 0.5 GB** (2026-10-03): 176 files in 93 groups (2024-08-18 → 08-20), all verified in 28 s (~18 MB/s), 0 deleted. Layout: `images\` 169 files (82 of them Live Photo `.MOV`), `videos\` 7 real videos

### Phase 3: UI
- [x] `app.py` window as in §5 (tkinter), with a background worker thread that owns the iPhone connection. Settings saved; Stop safely; red banner on disconnect; confirmation popup before any run with deletion; next chunk shown automatically after each run. Launcher: `SafeMove.cmd`
- [x] Real run from the window in **Test mode, 0.7 GB** (2026-10-03, started by the user): 227 files in 42 s. 176 were recognized as **already on PC** from the earlier CLI run (no duplicates), 51 new, 0 deleted, 0 failed

### Phase 4: Deletion enabled
- [x] Turn on per-group deletion after verification
- [x] **First real move from the window (2026-10-03, 1 GB, started by the user):** 162 files deleted, then the iPhone disconnected while copying `IMG_1068`. Check afterwards: all 162 deleted files are on the PC with identical SHA-256, `IMG_1068` is still on the iPhone, no partial files. **Bug found:** the iPhone stalled ~19 s on deleting `IMG_1067` (pair), reported success but kept both files, then disconnected. Nothing was lost, since the files were in both places, but the manifest said "deleted"
- [x] **Fix:** `delete()` now treats the "partly failed" code (S_FALSE) as a failure, **and re-checks that the file is really gone** (while making sure the iPhone still answers, so a disconnect can't pass for a successful delete)
- [x] **Edited items can't be deleted over USB** (2026-10-03). The edited video `IMG_1000` (`.MOV` original + `IMG_E1000.MOV` render + `.AAE` edit file) came back after a replug: first after deleting the 2 videos, then again after deleting all 3 files (`.AAE` first). The iPhone also hung while deleting the render. All other deletions (160 files) stayed deleted. The in-session USB file list is not reliable: the real state only shows after a reconnect
- [x] Retest (2026-10-04) with the **Photos app force-closed** the whole time: all 3 files of `IMG_1000` were re-verified against the PC copies, deleted (`.AAE` → render → original), and confirmed gone in the session. After a replug, all 3 were back again. So it isn't caused by Photos being open: the iPhone restores edited items. All other deleted files (349) stayed deleted
- [x] **Decision (user, option A):** edited groups (any `IMG_E…` or `.AAE`) are copied and verified, including the `.AAE` to keep the edit information, but **never deleted**. They're recorded in the manifest as `edited, kept on iPhone`, skipped by later plans, and listed in `logs\edited-items-to-delete.txt` so the user can delete them in the Photos app. About ~930 edited items exist on the phone
- [ ] **Manual disconnect test:** start a chunk and pull the cable mid-video. Check that the banner appears, there are no partial files, the phone still has the file, and Start resumes correctly
- [ ] Run a real small chunk (1 GB) with deletion. Compare the iPhone and the PC

### Phase 5: Normal use
- [ ] Use 10 GB chunks
- [x] **Built** (2026-10-04) with `python build_portable.py` → `dist\SafeMove-portable.zip` (13.9 MB). All 33 program files (`.exe/.dll/.pyd`) are signed by the PSF or Microsoft. Unused Tcl extras (dde, registry, tix, nmake helper) are left out because they were the only unsigned files. Self-test is part of the build. Tested on this laptop **with Smart App Control on**: unzipped to the user folder, launched with `SafeMove.cmd`, connected to the iPhone and planned a chunk
- [x] **Portable package** `SafeMove-portable.zip`, built by a script and tested on this laptop:
  ```
  SafeMove\
    SafeMove.cmd        ← double-click (starts the window with pythonw, no console)
    python\                 ← official Python *embeddable* package (signed by the PSF)
      + tkinter files copied from the full Python install (_tkinter.pyd, tcl/tk DLLs, tcl\ folder, also signed)
    lib\comtypes\           ← pure Python, no compiled files
    safemove\           ← our code
  ```
  - No unsigned .exe/.dll anywhere (that rules out PyInstaller and similar tools), so Smart App Control doesn't block it
  - Unzip into the user folder (e.g. `C:\Users\<you>\SafeMove`), not `Program Files`: comtypes writes small generated files next to itself on first run
  - Requirement on the other laptop: the iPhone shows up in Explorer under "This PC" (Windows installs the Apple driver automatically the first time the iPhone is plugged in)
- [x] **Installable** (2026-10-04): `Install.cmd` in the zip runs `safemove.install` with the signed `pythonw.exe`. It copies to `%LOCALAPPDATA%\Programs\SafeMove` (per user, no admin), creates Desktop + Start menu shortcuts with an icon (`make_icon.py` → `app.ico`), and registers an entry in Settings → Apps with uninstall. Updating = running `Install.cmd` from a newer zip. No new `.exe` is created, so Smart App Control has nothing to block. A real `.exe`/installer would need a paid code-signing certificate. Tested here: install, launch from the Start menu shortcut (connects to the iPhone), update
- [x] Only one copy of the app can run at a time (named mutex)
- [ ] Test the zip on the other laptop: scan, a 1 GB chunk in Test mode, then normal use

---

## 9. Later ideas (not in v1)

- Copy to an external SSD with a second verification. **Strongly recommended**, since after deletion the laptop holds the only copy
- Use the date stored inside the photo (EXIF / QuickTime metadata) instead of the date reported by the iPhone
- Chunks by date range ("everything before 2023") as well as by size
- Spot duplicates across runs by hash

---

## 10. Risks and things to watch

| Risk | Mitigation |
|---|---|
| Deleting through WPD might behave unexpectedly on some iOS versions | The Phase 1 deletion gate tests this with throwaway photos |
| The iPhone locks during long transfers and access drops | Before big runs, set **Auto-Lock → Never** on the phone; disconnects are handled anyway |
| The Windows AutoPlay or Photos import pops up and grabs the device | Close it if it appears; optionally disable AutoPlay for the iPhone |
| COM/WPD calls are sensitive to threading | All device calls run on one dedicated worker thread |
| The first listing after connecting is slow: the iPhone prepares file details on demand (seen: about 20,000 files in 37 s once prepared, 5–30 files/s before that) | Show listing progress; the details are cached by the phone after the first time |
| The iPhone drops off USB during long operations (seen during a read-only listing) | Every device call is wrapped; the run stops cleanly and resumes on reconnect |
| iPhone setting "Transfer to Mac or PC: **Automatic**" converts HEIC/HEVC to JPG/H.264 during transfer (slow, and not the originals) | Set **Settings → Apps → Photos → Transfer to Mac or PC → Keep Originals** before any run |
| Dates reported by the iPhone may be the transfer date rather than the capture date | Check in Phase 1. If they're wrong, move EXIF dates into v1 |
| Laptop disk failure after deletion | Back up `C:\SafeMove` to an external drive (see §9) |

## 11. Before every real run (checklist)
1. Cable connected, iPhone unlocked, "Trust" accepted, Auto-Lock set to Never
2. Laptop plugged into power (no sleep in the middle of a run)
3. Check the destination and the free space in the app
4. After the run: look at the summary and handle any ✗ errors before the next run

---

## 12. After v1

- [x] **Month / day selection** (2026-10-04, user request): besides "oldest first, up to N GB", the window offers **Whole month** (list of months from folder names) and **One day** (days of the selected month, with file count and size). CLI: `--month YYYY-MM`, `--day YYYY-MM-DD`. Reads the month's folders plus only the **first** folder of the next month, for late-filed photos. Reading all 10 folders of October 2024 made September take 102 s; with only the first one it takes 0.4 s, same result (1,129 files, 4.88 GB). 7 new tests (26 total)
- [x] Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md` (also shipped in the zip), `.gitignore`
- [x] **Open-source preparation** (2026-10-04): MIT license, CONTRIBUTING, code of conduct, issue/PR templates, GitHub Actions tests; `model.py` split out so the engine and the tests don't need the Windows device API; **device report** (`safemove.report`) and a clear "unknown folder layout" message for other iPhone models
- [x] **Renamed to SafeMove** (2026-10-04): the name leaves room for other phones and cameras. Old settings, shortcuts, Apps entry and program folder are migrated or removed by the installer
- [x] **External drives** (2026-10-04): `drives.py`. The drive is remembered by its volume serial and followed to a new letter; the margin is 1 GB on non-Windows drives; FAT32 4 GB check before starting; clear message on unplug mid-run; "Safely Remove Hardware" reminder. A test found a real bug: with the drive missing, the manifest tried to create its folder at startup and crashed; it now creates it on first write. 10 new tests (36 total). Not yet tried with a real external drive

## 13. Next steps

- [ ] **Android phones**: device profiles (detection, photo folders such as `DCIM\Camera` / `Pictures\Screenshots` / SD card, dates from file names, grouping, deletion rules), then test mode → small move on the author's Android phone, and verify that deletions stick after a reconnect
- [ ] **Cameras** (PTP/MTP, `DCIM\100XXXXX`) as another device profile
- [ ] **Second copy**: copy to the PC and an external drive, verify both, then delete from the phone
- [ ] Try the external-drive features on a real USB disk (letter change, unplug mid-run, FAT32 stick)
