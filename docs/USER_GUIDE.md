# SafeMove: user guide

SafeMove moves your photos and videos from the iPhone to this PC, or straight to an external drive, through the USB cable: **oldest first a few GB at a time, or a whole month, or one day**. (Android phones and cameras are planned.) Each photo or video is deleted from the iPhone **only after its copy on the PC has been checked**. If anything interrupts it (cable, locked phone, closed app), nothing is lost, and the next run continues where it stopped.

**Contents:** [Install](#1-install) · [Prepare the iPhone](#2-prepare-the-iphone-once) · [The window](#3-the-window) · [First run](#4-first-run-test-mode) · [Everyday use](#5-everyday-use) · [Edited photos](#6-edited-photos-and-videos) · [Interruptions](#7-if-something-goes-wrong) · [Where things are](#8-where-things-are) · [Troubleshooting](#9-troubleshooting) · [FAQ](#10-faq)

---

## 1. Install

You need: Windows 10 or 11, the iPhone cable, and the file `SafeMove-portable.zip`.

1. **Only if you downloaded the zip** (rather than copying it from a USB stick): right-click it → **Properties** → tick **Unblock** → **OK**.
2. Unzip it anywhere and open the folder.
3. Double-click **`Install.cmd`**. A small window confirms the installation. No admin password is needed.
4. **SafeMove** now appears on the **Desktop** and in the **Start menu**.

| | |
|---|---|
| Update to a newer version | Run `Install.cmd` from the newer zip. Your photos, logs and settings are kept. |
| Uninstall | Settings → Apps → Installed apps → SafeMove → Uninstall. Your photos and logs are kept. |
| Use without installing | Double-click `SafeMove.cmd` in the unzipped folder. |

---

## 2. Prepare the iPhone (once)

| Setting on the iPhone | Why |
|---|---|
| **Settings → Apps → Photos → Transfer to Mac or PC → Keep Originals** | Otherwise the iPhone converts photos and videos while sending them: slower, and not your originals. |
| **Settings → Display & Brightness → Auto-Lock → Never** (while transferring) | A locked iPhone often drops the USB connection. |
| Connect the cable, unlock, tap **Trust** / **Allow** | Windows can't see the photos otherwise. |

Check: in Windows Explorer, **This PC → Apple iPhone → Internal Storage** should open and show folders like `202408__`.

---

## 3. The window

```
┌─ SafeMove ─────────────────────────────────────────────┐
│ iPhone        Connected: Apple iPhone · 70 photo folders   [Reconnect] │
│ Destination   C:\SafeMove                                    [Browse…]   │
│               Drive C: free space: 212.7 GB                            │
│ Move this time (•) Oldest first, up to [ 10 ] GB                       │
│                ( ) Whole month   [ 2024-08 ▼ ]                         │
│                ( ) One day       [ 2024-08-25 · 689 files · 2.57 GB ▼ ]│
│               → 2,369 files, 10.00 GB, 2024-08-18 → 2024-09-21         │
│ ☑ Test mode (copy only, don't delete from iPhone)                      │
│ ☐ Paranoid verify (read each file twice from the iPhone, slower)       │
│          [ Start ]   [ Stop safely ]   [ Open folder ]                 │
│ ███████████░░░░░░  4.10 / 10.00 GB (812 / 2,369 files)                 │
│ Current: IMG_1121.MOV · 21.4 MB/s · ~5 min left                        │
│ ┌ log ───────────────────────────────────────────────────┐             │
│ │ ✓ IMG_1100.HEIC + IMG_1100.MOV moved → C:\SafeMove\images\2024\08 │    │
│ └────────────────────────────────────────────────────────┘             │
└────────────────────────────────────────────────────────────┘
```

| Item | What it does |
|---|---|
| **iPhone** | Green = connected. Red = not connected: plug in, unlock, press **Reconnect**. |
| **Destination** | Where photos go: a folder on this PC (default `C:\SafeMove`) or on an external drive (see [external drive](#moving-straight-to-an-external-drive)). The line below shows the drive and its free space. It turns red when fewer than 20 GB (Windows drive) or 1 GB (other drives) would be left after the run; Start is then blocked. |
| **Move this time** | What this run moves (see below). The grey line under it shows exactly what will be moved: number of files, size, date range. |
| • **Oldest first, up to N GB** | The oldest photos and videos still on the iPhone, up to that size. |
| • **Whole month** | Everything taken in that month (by the date the photo was taken). The list shows every month that still has photos on the iPhone. No size limit: check the size in the grey line. |
| • **One day** | Everything taken on one day. The list shows the days of the month selected above that still have photos, with the number of files and size for each. |
| **Test mode** | Copies and checks, **never deletes** from the iPhone. Use it for your first run on each laptop. |
| **Paranoid verify** | Reads each file a second time from the iPhone and compares. Safest, but twice as slow. Not needed normally. |
| **Start** | Starts the run. With test mode off, it asks for confirmation first. |
| **Stop safely** | Finishes the photo/video in progress, then stops. Nothing is lost. |
| **Open folder** | Opens the destination in Explorer. |
| **Log** | Green ✓ moved · orange ✎ edited item kept on the iPhone or ⚠ warning · red ✗ problem. |

---

## 4. First run (test mode)

1. Start SafeMove. Wait until the iPhone line is green and the grey line shows the chunk.
2. Set **Move this time** to **1** GB and leave **Test mode** ticked.
3. Press **Start**, then wait for the summary popup (about a minute).
4. Press **Open folder** and look in `images\` and `videos\`: open a few photos and play a video.

Nothing was deleted from the iPhone. Those files are now recognized as **already on the PC**, so the next real run deletes them from the iPhone without copying them again.

---

## 5. Everyday use

1. Plug in, unlock the iPhone (Auto-Lock → Never), start SafeMove.
2. Choose what to move and **untick Test mode**:
   - **Oldest first, up to 10 GB** (about 10 minutes) to work through the library in order, or
   - **Whole month** (e.g. 2024-08) or **One day** to move a specific period. Afterwards that month or day is done, which is easy to check in the Photos app.
3. Press **Start** and confirm the popup.
4. Leave the cable alone until the summary popup appears:

   > DONE: 2,369 files (10.00 GB) safe on the PC, 2,350 deleted from the iPhone, 0 groups failed, in 0:09:41. 4 edited item(s) kept on the iPhone

5. The next chunk appears automatically. Press **Start** again, or stop for today.

**Good habits**
- Keep the laptop **plugged into power**.
- After a session, **unplug and replug once**, then glance at the Photos app. The iPhone sometimes only shows its real state after a reconnect.
- **Back up `C:\SafeMove`** (e.g. to an external drive). Once a photo is moved, the PC holds the only copy.

### Moving straight to an external drive

You can move photos directly to an external disk or USB stick: plug it in, press **Browse…** and choose a folder on it (e.g. `E:\Photos`). The line under the destination shows which drive it is, for example `E: “Samsung T7” (exFAT, external drive) · free space: 812 GB`.

- **The drive letter can change** (E: today, F: tomorrow). SafeMove remembers the drive itself and follows it to its new letter automatically.
- **Unplugged drive:** the destination line turns red ("not connected: plug it in") and Start is blocked. Plug it back in and the line turns green again within a few seconds.
- **Free space:** on an external drive SafeMove keeps at least 1 GB free (20 GB on the Windows drive).
- **FAT32 drives** (many USB sticks) can't store files of 4 GB or more, and long 4K videos often are that big. SafeMove shows "⚠ FAT32" and won't start if the selection contains such a file. Reformat the drive as **exFAT** (this erases it) or choose another destination.
- **Unplugged during a run:** the run stops and says the drive was disconnected. Nothing is lost: what wasn't finished is still on the phone.
- **When the run is done,** use **Safely Remove Hardware** (USB icon in the taskbar) before unplugging the drive. SafeMove reminds you.
- The logs and the list of moved files are kept **on that drive** (`<destination>\logs`), so they travel with it.

---

## 6. Edited photos and videos

If you edited a photo or video in the Photos app (crop, filter, trim…), the iPhone keeps the original, the edited version and an edit file. **The iPhone doesn't let edited items be deleted over USB**: it puts them back. So SafeMove:

- copies all their files to the PC and checks them, so both the original and the edited version are safe, plus the `.AAE` edit file
- **leaves them on the iPhone**, shows them in orange with ✎ in the log, and doesn't pick them again next time
- lists them in **`C:\SafeMove\logs\edited-items-to-delete.txt`**, for example:

  ```
  2024-08  IMG_1000  (iPhone folder 202408__)  ->  C:\SafeMove\videos\2024\08\IMG_1000.MOV | …
  ```

**To delete them:** in the Photos app, go to that month, select them, delete, and then empty **Albums → Recently Deleted**. Before deleting, you can check that the files are in the folder shown in the list.

---

## 7. If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| **Red banner: "iPhone disconnected… Nothing lost"** | The connection dropped. The item it was working on is still on the iPhone, and everything before it is safely moved. | Replug, unlock, press **Reconnect**, then **Start**. It continues. |
| Progress stuck on one file for minutes | The iPhone stopped answering. | Close the app (safe: nothing is deleted before a file is fully checked), unplug, wait 10 s, replug, unlock, start again. |
| ✗ "failed verification" in red | A file didn't arrive complete. | Nothing to do: it stays on the iPhone and will be retried next run. |
| ⚠ "could not be deleted from the iPhone" | Safe on the PC, but the iPhone refused the delete. | Nothing to do: it's deleted next run. |
| "Not enough free space" | Fewer than 20 GB (Windows drive) or 1 GB (other drive) would be left. | Choose a smaller chunk or free up space. |
| Red: "Destination drive … is not connected" | The external drive is unplugged. | Plug it in; SafeMove finds it again, even under another letter. |
| "can't be stored on this FAT32 drive" | The selection has a video of 4 GB or more. | Reformat the drive as exFAT, or choose another destination. |
| "The destination drive was disconnected" | It was unplugged during the run. | Nothing lost. Plug it back in and press Start. |
| "Connect and unlock the iPhone" | No iPhone found. | Cable, unlock, Trust, then **Reconnect**. Check Explorer → This PC. |
| "SafeMove is already open" | Only one window can run at a time. | Use the one in the taskbar. |

You can always check a run: every file is listed in `logs\manifest.csv`.

---

## 8. Where things are

| What | Where |
|---|---|
| Your photos | `C:\SafeMove\images\YYYY\MM\` (Live Photo clips sit next to their photo) |
| Your videos | `C:\SafeMove\videos\YYYY\MM\` |
| One log per run | `C:\SafeMove\logs\2026-10-04_10-15-00.txt` |
| Every moved file, with its fingerprint | `C:\SafeMove\logs\manifest.csv` (opens in Excel) |
| Edited items to delete by hand | `C:\SafeMove\logs\edited-items-to-delete.txt` |
| Settings | `%APPDATA%\SafeMove\settings.json` |
| The installed app | `%LOCALAPPDATA%\Programs\SafeMove` |

If two different photos have the same name (the iPhone restarts numbering after IMG_9999), the second one is saved as `IMG_0001_2.HEIC`. Nothing is ever overwritten.

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| "photo folders have names this version doesn't recognize" | Your iPhone model or iOS version stores photos differently. Nothing was changed. Run **SafeMove - device report** from the Start menu and attach the file it creates (on your Desktop) to a GitHub issue, so support can be added. |
| The app doesn't start | Run `SafeMove (console).cmd` from the zip folder: it shows the error message. |
| `Install.cmd` is blocked by Windows | Unblock the zip (see [Install](#1-install)) and unzip it again. |
| The first "Preparing the next chunk…" takes minutes | Normal right after plugging in: the iPhone is preparing its file list. It's fast afterwards. |
| The iPhone keeps disconnecting | Auto-Lock → Never, keep the screen on, try another cable or USB port, avoid USB hubs. |
| Photos look converted (JPG instead of HEIC) | Set **Keep Originals** (see [Prepare the iPhone](#2-prepare-the-iphone-once)). |
| A photo deleted by the app is still on the iPhone | Replug the cable: the iPhone may show old information until it reconnects. If it's still there, run the app again; it recognizes the photo as already on the PC and deletes it again. Edited items always stay (see [Edited photos](#6-edited-photos-and-videos)). |

---

## 10. FAQ

**Can I lose photos?** The app deletes a photo only after its copy on the PC has the exact same size and fingerprint as what the iPhone sent, and has been read back from disk. In all tests, every deleted photo was found intact on the PC. The remaining risk is the PC itself (disk failure, accidental deletion), so keep a backup.

**Do deleted photos go to "Recently Deleted" on the iPhone?** This hasn't been checked. Assume they don't.

**Can I stop at any time?** Yes. **Stop safely** is the clean way, but even closing the app or pulling the cable doesn't lose anything.

**Why does a month or day still show a few items after I moved it?** Those are edited items (kept on purpose, see [Edited photos](#6-edited-photos-and-videos)) or items that failed and will be retried. Edited items that are already safe on the PC aren't counted again.

**A photo is in the wrong month folder on the iPhone. Is it still found?** Yes. Month and day are based on the date the photo was taken, and the app also looks in the first folder of the following month, where late-filed photos end up.

**Can I choose another drive?** Yes, with **Browse…**, including an external drive (see [external drive](#moving-straight-to-an-external-drive)). Keep using the same destination afterwards, so files already moved are recognized.

**I used "iPhone Mover" before. What happens?** SafeMove is the same app under a new name. Installing SafeMove removes the old shortcuts and program, and takes over your settings (including your destination, e.g. `C:\iPhone`). Photos and logs are untouched.

**Can I use it on two laptops?** Yes. Each laptop has its own archive and logs. Don't move the same iPhone on two laptops at the same time.

**Why isn't it a normal .exe?** Windows Smart App Control blocks programs that aren't signed by a known publisher. SafeMove runs on the official, signed Python instead, so it works without a paid code-signing certificate.

**Which files are moved?** Photos (HEIC, HEIF, JPG, JPEG, PNG, GIF, DNG, TIF, TIFF, WEBP), videos (MOV, MP4, M4V, 3GP, AVI) and the `.AAE` edit files that belong to them. Nothing else is touched.
