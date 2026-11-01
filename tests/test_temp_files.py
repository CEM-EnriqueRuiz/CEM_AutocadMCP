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


# --- exports\ (known gap 16, docs/decisions/0006): its own rule, outside the 50 MB cap ------------------------

def exports_scenario(root):
    """A folder as a day of exports leaves it; ages in days. Returns (kept, deleted) by the exports rule."""
    e = root / "exports"
    kept = [write(e / "newest.json", 1000, 0.1),  # alone over the folder's size cap: it must survive
            write(e / "second.failed.json", 10, 0.2),
            write(e / "third.json", 10, 0.3),
            write(e / "running.json.partial", 10, 0.05),  # a job of another server process
            write(root / "b.log", 100, 2), write(root / "c.log", 100, 1)]
    deleted = [write(e / "fourth.json", 10, 0.4),  # beyond the last 3
               write(e / "old.json", 10, 10),  # beyond 7 days
               write(e / "stale.json.partial", 10, 9),  # a crashed job
               write(root / "a.log", 100, 3)]  # the rest of the folder still has its 50 MB cap (here 250 bytes)
    return kept, deleted


def test_exports_keep_the_last_three_outside_the_size_cap(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path, max_bytes=250)
    kept, deleted = exports_scenario(folder.root)
    folder.prune()
    assert [p.name for p in kept if not p.exists()] == []
    assert [p.name for p in deleted if p.exists()] == []


def test_the_newest_export_and_the_newest_complete_one_survive_any_age(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path)
    e = folder.root / "exports"
    newest = write(e / "retry.failed.json", 10, 9)
    complete = write(e / "good.json", 10, 10)
    older = write(e / "older.json", 10, 12)
    folder.prune()
    assert newest.exists() and complete.exists() and not older.exists()


def test_never_more_than_three_exports_even_when_the_newest_ones_failed(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path)
    e = folder.root / "exports"
    f1, f2, f3 = (write(e / f"f{i}.failed.json", 10, i / 10) for i in (1, 2, 3))
    good = write(e / "good.json", 10, 0.4)
    folder.prune()
    assert sorted(p.name for p in e.iterdir()) == ["f1.failed.json", "f2.failed.json", "good.json"]
    assert not f3.exists()


def test_prune_exports_alone_leaves_the_rest_of_the_folder(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path, max_bytes=1)
    log = write(folder.root / "old.log", 10, 9)
    surplus = [write(folder.root / "exports" / f"x{i}.json", 10, i / 10) for i in range(5)]
    folder.prune_exports()
    assert log.exists()
    assert [p.exists() for p in surplus] == [True, True, True, False, False]


def qa1_scenario(e):
    """QA-1: the newest export is complete, a second complete one is 10 days old: it goes (at most 3, within 7 days)."""
    keep = [write(e / "newest.json", 10, 0.1), write(e / "retry.failed.json", 10, 0.2)]
    drop = [write(e / "old-good.json", 10, 10)]
    return keep, drop


def test_an_old_second_complete_export_is_not_kept_when_the_newest_is_complete(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path)
    keep, drop = qa1_scenario(folder.root / "exports")
    folder.prune()
    assert all(p.exists() for p in keep) and not any(p.exists() for p in drop)
