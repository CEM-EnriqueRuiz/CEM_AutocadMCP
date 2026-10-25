"""TempFolder follows root decision 0031 §2-4: %TEMP%\\Cemengal\\<App>\\, one log per day, an artefact
subfolder per kind, and a prune on the first write of each process (older than 7 days, then the oldest
until under 50 MB; locked files skipped; never raises)."""
import os
import tempfile
import time
from datetime import date
from pathlib import Path

import pytest

from autocad_mcp import temp_files
from autocad_mcp.temp_files import TempFolder

DAY = 24 * 3600


def write(path: Path, size: int, age_days: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    stamp = time.time() - age_days * DAY
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def folder(tmp_path):
    return TempFolder("AutocadMCP", base=tmp_path)


def test_default_root_is_cemengal_app_in_the_local_temp_folder():
    assert TempFolder().root == Path(tempfile.gettempdir()) / "Cemengal" / "AutocadMCP"


def test_log_path_is_one_file_per_day_and_creates_the_folder(folder):
    path = folder.log_path("diag", day=date(2026, 10, 24))
    assert path == folder.root / "diag-20261024.log"
    assert path.parent.is_dir()
    assert folder.log_path("actions", ext=".jsonl", day=date(2026, 1, 2)).name == "actions-20260102.jsonl"


def test_log_path_defaults_to_today(folder):
    assert folder.log_path("live-test").name == f"live-test-{date.today():%Y%m%d}.log"


def test_artefact_dir_is_a_subfolder_per_kind(folder):
    path = folder.artefact_dir("Screenshots")
    assert path == folder.root / "Screenshots"
    assert path.is_dir()


def test_prune_deletes_files_older_than_seven_days_in_every_subfolder(folder):
    old_log = write(folder.root / "diag-20261001.log", 10, age_days=8)
    old_shot = write(folder.root / "Screenshots" / "a.png", 10, age_days=30)
    recent = write(folder.root / "diag-20261023.log", 10, age_days=1)
    folder.prune()
    assert not old_log.exists()
    assert not old_shot.exists()
    assert recent.exists()


def test_prune_then_deletes_the_oldest_until_under_the_size_limit(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path, max_bytes=250)
    oldest = write(folder.root / "a.log", 100, age_days=3)
    middle = write(folder.root / "Kind" / "b.png", 100, age_days=2)
    newest = write(folder.root / "c.log", 100, age_days=1)
    folder.prune()
    assert not oldest.exists()
    assert middle.exists() and newest.exists()


def test_prune_skips_a_locked_file_and_does_not_raise(folder):
    locked = write(folder.root / "in-use.log", 10, age_days=9)
    other = write(folder.root / "other.log", 10, age_days=9)
    with open(locked, "rb"):  # Windows refuses to delete an open file
        folder.prune()
    assert locked.exists()
    assert not other.exists()


def test_prune_never_raises(folder, monkeypatch):
    write(folder.root / "old.log", 10, age_days=9)

    def boom(self, *args, **kwargs):
        raise OSError("disk on fire")

    monkeypatch.setattr(Path, "unlink", boom)
    folder.prune()  # must not raise
    TempFolder("AutocadMCP", base=folder.root / "missing").prune()


def test_first_write_of_the_process_prunes_once(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(TempFolder, "prune", lambda self, now=None: calls.append(self.root))
    first = TempFolder("AutocadMCP", base=tmp_path)
    first.log_path("diag")
    first.log_path("live-test")
    first.artefact_dir("Screenshots")
    TempFolder("AutocadMCP", base=tmp_path).log_path("diag")  # another instance, same folder
    assert calls == [first.root]


def test_refuses_a_folder_under_acc(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path / "DC" / "ACCDocs" / "Project")
    with pytest.raises(ValueError):
        folder.log_path("diag")
    assert not (tmp_path / "DC").exists()


def test_the_helper_knows_its_app_name():
    assert temp_files.APP == "AutocadMCP"
