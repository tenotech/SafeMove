"""Command-line runner for one chunk (the window in app.py does the same with buttons).

    python -m safemove.cli --chunk-gb 1 --test-mode       copy + verify only
    python -m safemove.cli --chunk-gb 10 --move           copy + verify + delete from the iPhone
    python -m safemove.cli --month 2024-08 --move         everything taken in August 2024
    python -m safemove.cli --day 2024-08-18 --test-mode   everything taken on that day
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .drives import min_free_bytes, volume_of
from .grouping import make_plan
from .mover import GB, Event, Mover, Options, describe
from .records import Manifest
from .wpd import DeviceError, IPhone


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Move the oldest photos/videos from the iPhone to the PC.")
    ap.add_argument("--dest", default=r"C:\SafeMove")
    what = ap.add_mutually_exclusive_group()
    what.add_argument("--chunk-gb", type=float, default=10.0, help="oldest photos/videos first, up to N GB")
    what.add_argument("--month", help="everything taken in this month, YYYY-MM")
    what.add_argument("--day", help="everything taken on this day, YYYY-MM-DD")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--test-mode", action="store_true", help="copy + verify only, never delete")
    mode.add_argument("--move", action="store_true", help="delete each group from the iPhone once verified")
    ap.add_argument("--paranoid", action="store_true", help="read each file twice from the iPhone")
    ap.add_argument("--min-free-gb", type=float, default=None,
                    help="free space to keep on the destination drive (default: 20 GB on the Windows drive, 1 GB elsewhere)")
    args = ap.parse_args()

    try:
        phone = IPhone.connect()
    except DeviceError as e:
        print(f"✗ {e}")
        return 1
    with phone:
        print(f"✓ Connected: {phone.name}")
        kept = Manifest(Path(args.dest) / "logs" / "manifest.csv").kept_edited()
        selection = (("month", args.month) if args.month else ("day", args.day) if args.day
                     else ("size", int(args.chunk_gb * GB)))
        plan = make_plan(phone, selection,
                         on_progress=lambda folder, n: print(f"  scanned {folder}: {n:,} files so far"),
                         already_kept=kept)
        if not plan.groups:
            print(f"Nothing to move for {plan.label}.")
            return 0
        print(f"{plan.label}: {plan.file_count} files in {len(plan.groups)} groups, {plan.size / GB:.2f} GB, "
              f"{plan.first_date:%Y-%m-%d} → {plan.last_date:%Y-%m-%d}")

        last_pct = [-1]

        def on_event(e: Event) -> None:
            if e.text:
                print(e.text)
            elif e.bytes_total:
                pct = int(100 * e.bytes_done / e.bytes_total)
                if pct != last_pct[0]:
                    last_pct[0] = pct
                    print(f"  {pct:3d}%  {e.files_done}/{e.files_total} files  {e.current}", flush=True)

        volume = volume_of(args.dest)
        margin = int(args.min_free_gb * GB) if args.min_free_gb is not None else min_free_bytes(volume, 20, 1)
        options = Options(Path(args.dest), test_mode=args.test_mode, paranoid=args.paranoid, min_free_bytes=margin)
        summary = Mover(phone, options, on_event).run(plan)
        print(describe(summary))
        print(f"Log: {summary.log_path}")
        if volume and volume.external and summary.files_moved:
            print(f"Before unplugging drive {volume.letter}, use 'Safely Remove Hardware' in the taskbar.")
        return 0 if summary.outcome == "done" else 2


if __name__ == "__main__":
    sys.exit(main())
