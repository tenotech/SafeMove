import csv
import datetime as dt
import threading
from pathlib import Path

import pytest

from safemove.grouping import make_groups, plan_chunk
from safemove.mover import Mover, Options
from safemove.paths import target_dir

from fake_phone import FakePhone

T0 = dt.datetime(2024, 8, 18, 10, 0)


def at(minutes: int) -> dt.datetime:
    return T0 + dt.timedelta(minutes=minutes)


@pytest.fixture
def phone() -> FakePhone:
    p = FakePhone()
    p.add("202408__", "IMG_0578.MOV", b"video-0578" * 10, at(0))     # edited video: original
    p.add("202408__", "IMG_E0578.MOV", b"edit-0578" * 10, at(0))     # rendered edit
    p.add("202408__", "IMG_0578.AAE", b"<xml/>", at(60 * 24 * 90))   # edit file, dated when edited
    p.add("202408__", "IMG_0579.HEIC", b"photo-0579" * 10, at(1))    # Live Photo pair
    p.add("202408__", "IMG_0579.MOV", b"live-0579" * 10, at(1))
    p.add("202408__", "IMG_0590.AAE", b"<orphan/>", at(3))           # edit file without media: never touched
    p.add("202408__", "NOTES.TXT", b"not media", at(3))              # not media: never listed
    p.add("202408__", "WHKG8552.JPG", b"whatsapp" * 10, at(2))       # standalone
    p.add("202409__", "IMG_0700.PNG", b"screenshot" * 10, at(60 * 24 * 30))
    p.add("202410__", "IMG_0800.HEIC", b"october" * 10, at(60 * 24 * 60))
    return p


def run(phone, root: Path, chunk: int = 10**9, **opts):
    mover = Mover(phone, Options(root=root, min_free_bytes=0, **{"test_mode": False, **opts}))
    return mover.run(plan_chunk(phone, chunk)), mover


def archive_files(root: Path) -> set[str]:
    return {p.name for p in root.rglob("*") if p.is_file() and "logs" not in p.parts}


def manifest_rows(root: Path) -> list[dict]:
    with open(root / "logs" / "manifest.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---- grouping and planning ---------------------------------------------------

def test_groups_keep_pairs_together(phone):
    groups = make_groups(phone.list_files())
    assert [g.label for g in groups] == [
        "IMG_0578.AAE + IMG_0578.MOV + IMG_E0578.MOV",
        "IMG_0579.HEIC + IMG_0579.MOV",
        "WHKG8552.JPG",
        "IMG_0700.PNG",
        "IMG_0800.HEIC",
    ]


def test_non_media_is_never_listed(phone):
    assert "NOTES.TXT" not in {f.name for f in phone.list_files()}


def test_edited_item_is_copied_but_stays_on_phone(phone, tmp_path):
    summary, _ = run(phone, tmp_path)
    folder = tmp_path / "videos" / "2024" / "08"
    # the .AAE is dated 3 months later, but lands next to its video (group date)
    assert {p.name for p in folder.iterdir()} >= {"IMG_0578.AAE", "IMG_0578.MOV", "IMG_E0578.MOV"}
    assert {"IMG_0578.AAE", "IMG_0578.MOV", "IMG_E0578.MOV"} <= phone.names()  # never deleted
    assert not set(phone.deleted) & {"IMG_0578.AAE", "IMG_0578.MOV", "IMG_E0578.MOV"}
    assert summary.edited_kept == ["IMG_0578.AAE + IMG_0578.MOV + IMG_E0578.MOV"]
    assert "IMG_0578" in summary.edited_list_path.read_text(encoding="utf-8")
    # next time it is not picked again: nothing else is left, so the plan is empty
    from safemove.records import Manifest
    kept = Manifest(tmp_path / "logs" / "manifest.csv").kept_edited()
    assert plan_chunk(phone, 10**9, already_kept=kept).groups == []


def test_test_mode_does_not_remember_edited_items(phone, tmp_path):
    run(phone, tmp_path, test_mode=True)
    from safemove.records import Manifest
    assert Manifest(tmp_path / "logs" / "manifest.csv").kept_edited() == set()


def test_chunk_takes_oldest_groups_without_splitting(phone):
    pair = 200  # each pair is ~190-200 bytes
    plan = plan_chunk(phone, chunk_bytes=pair + 50)
    assert [g.label for g in plan.groups] == ["IMG_0578.AAE + IMG_0578.MOV + IMG_E0578.MOV"]


def test_chunk_always_takes_at_least_one_group(phone):
    plan = plan_chunk(phone, chunk_bytes=1)
    assert len(plan.groups) == 1


def test_chunk_scans_only_needed_folders(phone):
    plan = plan_chunk(phone, chunk_bytes=100)
    # first folder already exceeds the chunk -> scan it plus one extra folder, not the third
    assert plan.folders_scanned == ["202408__", "202409__"]


# ---- moving ------------------------------------------------------------------

def test_happy_path_moves_everything(phone, tmp_path):
    summary, _ = run(phone, tmp_path)
    assert summary.outcome == "done"
    assert phone.names() == {"IMG_0578.AAE", "IMG_0578.MOV", "IMG_E0578.MOV"} | {"IMG_0590.AAE", "NOTES.TXT"}  # edited, lone .AAE, non-media
    assert (tmp_path / "videos" / "2024" / "08" / "IMG_0578.MOV").read_bytes() == b"video-0578" * 10
    assert (tmp_path / "images" / "2024" / "08" / "IMG_0579.HEIC").exists()
    assert (tmp_path / "images" / "2024" / "10" / "IMG_0800.HEIC").exists()
    assert not any((tmp_path / ".staging").iterdir())
    rows = manifest_rows(tmp_path)
    assert len(rows) == 8 and {r["status"] for r in rows} == {"deleted", "edited, kept on iPhone"}


def test_live_photo_video_stays_next_to_its_photo(phone, tmp_path):
    run(phone, tmp_path)
    assert (tmp_path / "images" / "2024" / "08" / "IMG_0579.MOV").exists()
    assert not (tmp_path / "videos" / "2024" / "08" / "IMG_0579.MOV").exists()
    assert (tmp_path / "videos" / "2024" / "08" / "IMG_E0578.MOV").exists()  # real video + its edit


def test_test_mode_never_deletes(phone, tmp_path):
    before = phone.names()
    summary, _ = run(phone, tmp_path, test_mode=True)
    assert summary.outcome == "done" and summary.files_deleted == 0
    assert phone.names() == before and phone.deleted == []
    assert len(archive_files(tmp_path)) == 8


def test_disconnect_mid_file_keeps_group_on_phone(phone, tmp_path):
    phone.disconnect_on = "IMG_0579.MOV"  # second file of the Live Photo
    summary, _ = run(phone, tmp_path)
    assert summary.outcome == "disconnected"
    assert phone.deleted == []  # first group is edited (kept), second one was interrupted
    assert {"IMG_0579.HEIC", "IMG_0579.MOV"} <= phone.names()  # Live Photo fully on the phone
    assert "IMG_0579.MOV" not in archive_files(tmp_path)  # no partial file anywhere
    assert not any((tmp_path / ".staging").iterdir())


def test_rerun_after_interruption_recognizes_copied_files(phone, tmp_path):
    phone.disconnect_on = "IMG_0579.MOV"
    run(phone, tmp_path)  # HEIC of the Live Photo reached the archive, MOV did not
    assert "IMG_0579.HEIC" in archive_files(tmp_path)

    phone.disconnect_on = None
    summary, _ = run(phone, tmp_path)
    assert summary.outcome == "done"
    assert phone.names() == {"IMG_0578.AAE", "IMG_0578.MOV", "IMG_E0578.MOV"} | {"IMG_0590.AAE", "NOTES.TXT"}
    heics = list((tmp_path / "images").rglob("IMG_0579*.HEIC"))
    assert [p.name for p in heics] == ["IMG_0579.HEIC"]  # no duplicate copy
    statuses = {r["source_name"]: r["status"] for r in manifest_rows(tmp_path)}
    assert statuses["IMG_0579.HEIC"] == "already on PC, deleted"


def test_same_name_different_content_gets_new_name(tmp_path):
    p = FakePhone()
    p.add("202408__", "IMG_0001.HEIC", b"first photo", at(0))
    p.add("202408_a", "IMG_0001.HEIC", b"another photo, same name", at(5))  # numbering restarted
    summary, _ = run(p, tmp_path)
    assert summary.outcome == "done"
    folder = tmp_path / "images" / "2024" / "08"
    assert (folder / "IMG_0001.HEIC").read_bytes() == b"first photo"
    assert (folder / "IMG_0001_2.HEIC").read_bytes() == b"another photo, same name"


def test_truncated_file_is_not_deleted_and_run_continues(phone, tmp_path):
    phone.truncate = {"IMG_0579.MOV"}
    summary, _ = run(phone, tmp_path)
    assert summary.outcome == "done"
    assert summary.groups_failed == ["IMG_0579.HEIC + IMG_0579.MOV"]
    assert {"IMG_0579.HEIC", "IMG_0579.MOV"} <= phone.names()  # whole Live Photo kept
    assert "IMG_0800.HEIC" not in phone.names()  # later groups still moved


def test_delete_failure_is_reported_not_fatal(phone, tmp_path):
    phone.fail_delete = {"WHKG8552.JPG"}
    summary, _ = run(phone, tmp_path)
    assert summary.outcome == "done" and len(summary.warnings) == 1
    assert "WHKG8552.JPG" in phone.names() and "WHKG8552.JPG" in archive_files(tmp_path)
    phone.fail_delete = set()
    run(phone, tmp_path)  # next run: recognized as already copied, then deleted
    assert "WHKG8552.JPG" not in phone.names()
    assert len(list(tmp_path.rglob("WHKG8552*.JPG"))) == 1


def test_not_enough_space_does_nothing(phone, tmp_path):
    mover = Mover(phone, Options(root=tmp_path, test_mode=False, min_free_bytes=10**18))
    summary = mover.run(plan_chunk(phone, 10**9))
    assert summary.outcome == "not enough space"
    assert phone.deleted == [] and archive_files(tmp_path) == set()


def test_stop_finishes_current_group_then_stops(phone, tmp_path):
    stop = threading.Event()
    seen = []

    def on_event(e):
        if e.level == "ok":
            seen.append(e.text)
            stop.set()  # press "Stop safely" right after the first group

    mover = Mover(phone, Options(root=tmp_path, test_mode=False, min_free_bytes=0), on_event, stop)
    summary = mover.run(plan_chunk(phone, 10**9))
    assert summary.outcome == "stopped"
    assert phone.deleted == ["IMG_0579.HEIC", "IMG_0579.MOV"]  # stopped after the first moved group


def test_staging_leftovers_are_cleared(phone, tmp_path):
    (tmp_path / ".staging").mkdir(parents=True)
    (tmp_path / ".staging" / "half_written.MOV").write_bytes(b"partial")
    run(phone, tmp_path, test_mode=True)
    assert not (tmp_path / ".staging" / "half_written.MOV").exists()


def test_target_dir_uses_folder_when_no_date(tmp_path):
    from safemove.model import DeviceFile
    f = DeviceFile("o1", "IMG_1.HEIC", "202503_a", 1, None, None, None)
    assert target_dir(tmp_path, f) == tmp_path / "images" / "2025" / "03"


# ---- month / day selection -----------------------------------------------------

from safemove.grouping import available_months, day_summary, make_plan  # noqa: E402


@pytest.fixture
def calendar_phone() -> FakePhone:
    p = FakePhone()
    p.add("202408__", "IMG_0001.HEIC", b"a" * 100, dt.datetime(2024, 8, 18, 10, 0))
    p.add("202408__", "IMG_0001.MOV", b"b" * 100, dt.datetime(2024, 8, 18, 10, 0))  # Live Photo
    p.add("202408__", "IMG_0002.HEIC", b"c" * 100, dt.datetime(2024, 8, 19, 9, 0))
    p.add("202409__", "IMG_0003.HEIC", b"d" * 100, dt.datetime(2024, 8, 31, 23, 59))  # filed in next month
    p.add("202409__", "IMG_0004.HEIC", b"e" * 100, dt.datetime(2024, 9, 2, 12, 0))
    p.add("202410__", "IMG_0005.HEIC", b"f" * 100, dt.datetime(2024, 10, 1, 8, 0))
    return p


def labels(plan):
    return [g.label for g in plan.groups]


def test_available_months_come_from_folder_names(calendar_phone):
    assert available_months(calendar_phone) == ["2024-08", "2024-09", "2024-10"]
    assert calendar_phone.listed_folders == []  # no file listing needed


def test_month_takes_whole_month_including_late_filed_photo(calendar_phone):
    plan = make_plan(calendar_phone, ("month", "2024-08"))
    assert labels(plan) == ["IMG_0001.HEIC + IMG_0001.MOV", "IMG_0002.HEIC", "IMG_0003.HEIC"]
    assert plan.folders_scanned == ["202408__", "202409__"]  # never 202410__
    assert plan.label == "month 2024-08"


def test_day_takes_only_that_day(calendar_phone):
    plan = make_plan(calendar_phone, ("day", "2024-08-18"))
    assert labels(plan) == ["IMG_0001.HEIC + IMG_0001.MOV"]
    assert make_plan(calendar_phone, ("day", "2024-08-31")).groups[0].label == "IMG_0003.HEIC"
    assert make_plan(calendar_phone, ("day", "2024-08-20")).groups == []


def test_day_summary_lists_days_with_photos(calendar_phone):
    assert day_summary(calendar_phone, "2024-08") == [
        (dt.date(2024, 8, 18), 2, 200), (dt.date(2024, 8, 19), 1, 100), (dt.date(2024, 8, 31), 1, 100)]


def test_month_across_year_end():
    p = FakePhone()
    p.add("202412__", "IMG_0010.HEIC", b"x" * 10, dt.datetime(2024, 12, 31, 12, 0))
    p.add("202501__", "IMG_0011.HEIC", b"y" * 10, dt.datetime(2025, 1, 1, 0, 5))
    assert labels(make_plan(p, ("month", "2024-12"))) == ["IMG_0010.HEIC"]
    assert labels(make_plan(p, ("month", "2025-01"))) == ["IMG_0011.HEIC"]


def test_moving_a_month_leaves_other_months_alone(calendar_phone, tmp_path):
    mover = Mover(calendar_phone, Options(root=tmp_path, test_mode=False, min_free_bytes=0))
    summary = mover.run(make_plan(calendar_phone, ("month", "2024-08")))
    assert summary.outcome == "done" and summary.files_deleted == 4
    assert calendar_phone.names() == {"IMG_0004.HEIC", "IMG_0005.HEIC"}
    assert (tmp_path / "images" / "2024" / "08" / "IMG_0003.HEIC").exists()  # filed by its date


def test_month_reads_only_first_folder_of_next_month():
    p = FakePhone()
    p.add("202409__", "IMG_0100.HEIC", b"x" * 10, dt.datetime(2024, 9, 5))
    p.add("202410__", "IMG_0101.HEIC", b"y" * 10, dt.datetime(2024, 9, 30, 23, 58))  # late-filed
    p.add("202410_a", "IMG_0102.HEIC", b"z" * 10, dt.datetime(2024, 10, 12))
    p.add("202410_b", "IMG_0103.HEIC", b"w" * 10, dt.datetime(2024, 10, 20))
    plan = make_plan(p, ("month", "2024-09"))
    assert labels(plan) == ["IMG_0100.HEIC", "IMG_0101.HEIC"]
    assert plan.folders_scanned == ["202409__", "202410__"]
