import datetime as dt
import json
import string
from pathlib import Path

import safemove.mover as mover_mod
from safemove.drives import GB, Volume, min_free_bytes, relocate, too_big_for
from safemove.grouping import make_plan
from safemove.mover import Mover, Options
from safemove.settings import Settings

from fake_phone import FakePhone

SYSTEM = Volume("C:\\", "", 111, "NTFS", removable=False, system=True)
T7 = Volume("F:\\", "Samsung T7", 222, "exFAT", removable=False, system=False)
STICK = Volume("G:\\", "STICK", 333, "FAT32", removable=True, system=False)


def test_destination_follows_drive_to_new_letter():
    # remembered as E:\Photos on drive 222, which now shows up as F:
    assert relocate(r"E:\Photos\Phone", 222, [SYSTEM, T7]) == r"F:\Photos\Phone"


def test_no_change_when_drive_has_same_letter():
    assert relocate(r"F:\Photos", 222, [SYSTEM, T7]) is None


def test_no_change_when_drive_not_connected_or_unknown():
    assert relocate(r"E:\Photos", 999, [SYSTEM, T7]) is None
    assert relocate(r"E:\Photos", 0, [SYSTEM, T7]) is None


def test_other_drive_at_old_letter_is_not_mistaken_for_ours():
    other = Volume("E:\\", "OTHER", 444, "NTFS", False, False)
    assert relocate(r"E:\Photos", 222, [SYSTEM, other, T7]) == r"F:\Photos"


def test_margin_is_large_on_windows_drive_small_elsewhere():
    assert min_free_bytes(SYSTEM, 20, 1) == 20 * GB
    assert min_free_bytes(T7, 20, 1) == 1 * GB
    assert min_free_bytes(None, 20, 1) == 20 * GB  # unknown: be careful


def test_fat32_rejects_files_of_4gb_or_more():
    files = [("small.HEIC", 3 * 2**20), ("long.MOV", 5 * GB), ("edge.MOV", 4 * GB)]
    assert too_big_for("FAT32", files) == ["long.MOV", "edge.MOV"]
    assert too_big_for("exFAT", files) == []
    assert too_big_for("NTFS", files) == []


def test_mover_refuses_fat32_when_a_file_is_too_big(tmp_path, monkeypatch):
    phone = FakePhone()
    phone.add("202408__", "IMG_0001.MOV", b"v" * 100, dt.datetime(2024, 8, 1))
    phone.files["o1"] = phone.files["o1"].__class__(**{**phone.files["o1"].__dict__, "size": 5 * GB})
    monkeypatch.setattr(mover_mod, "volume_of", lambda p: STICK)
    summary = Mover(phone, Options(root=tmp_path, test_mode=False, min_free_bytes=0)).run(
        make_plan(phone, ("size", 10 * GB)))
    assert summary.outcome == "file system limit"
    assert phone.deleted == [] and not (tmp_path / "videos").exists()


def test_mover_stops_cleanly_when_destination_drive_is_missing():
    used = {p.anchor[0] for p in map(Path, (f"{c}:\\" for c in string.ascii_uppercase)) if p.exists()}
    free_letter = next(c for c in reversed(string.ascii_uppercase) if c not in used)
    phone = FakePhone()
    phone.add("202408__", "IMG_0001.HEIC", b"x" * 10, dt.datetime(2024, 8, 1))
    summary = Mover(phone, Options(root=Path(f"{free_letter}:\\Photos"), test_mode=False, min_free_bytes=0)).run(
        make_plan(phone, ("size", GB)))
    assert summary.outcome == "destination not found"
    assert phone.deleted == []


def test_old_iphone_mover_settings_are_carried_over(tmp_path):
    legacy = tmp_path / "iPhoneMover" / "settings.json"
    legacy.parent.mkdir()
    legacy.write_text(json.dumps({"destination": r"C:\iPhone", "chunk_gb": 3, "test_mode": False,
                                  "min_free_gb": 20.0}), encoding="utf-8")
    new = tmp_path / "SafeMove" / "settings.json"
    s = Settings.load(new, legacy)
    assert s.destination == r"C:\iPhone" and s.chunk_gb == 3 and s.test_mode is False
    assert s.min_free_gb_other == 1.0  # new setting gets its default
    assert new.exists()  # saved under the new name


def test_new_settings_win_over_legacy(tmp_path):
    legacy, new = tmp_path / "old.json", tmp_path / "new.json"
    legacy.write_text(json.dumps({"destination": r"C:\iPhone"}), encoding="utf-8")
    new.write_text(json.dumps({"destination": r"F:\Photos"}), encoding="utf-8")
    assert Settings.load(new, legacy).destination == r"F:\Photos"
