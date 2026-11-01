"""docs/decisions/0006: export_drawing starts a background job and answers at once; get_export_status and
cancel_export follow it. The file goes to %TEMP%\\Cemengal\\AutocadMCP\\exports\\ (0003), is never overwritten,
and a limit ends the job as failed with the reason, never as a silently shorter file."""
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

import pythoncom
import pytest

from autocad_mcp import export as export_module
from autocad_mcp.export import ExportJob, ExportJobs, Limits, reserve
from autocad_mcp.temp_files import TempFolder
from export_drawing_fake import drawing_with_everything, total_entities
from fake_acad import FakeApp, FakeDocument, FakeEntity

NOW = datetime(2026, 11, 1, 10, 0, 0)


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "Cemengal" / "AutocadMCP" / "exports"


@pytest.fixture
def jobs(tmp_path):
    return ExportJobs(temp=TempFolder(base=tmp_path), now=lambda: NOW)


def start(jobs, app, doc, **limits):
    return jobs.start(app, doc.Name, doc.FullName, Limits(**limits))


class SlowCircle(FakeEntity):
    """A circle whose Radius waits for the test: the export is caught mid-walk."""

    def __init__(self, space, gate, entered):
        super().__init__(space, "AcDbCircle", "0", Center=(0.0, 0.0, 0.0), Normal=(0.0, 0.0, 1.0))
        self.gate, self.entered = gate, entered

    @property
    def Radius(self):
        self.entered.set()
        assert self.gate.wait(10)
        return 1.0


def with_slow_circle(doc):
    gate, entered = threading.Event(), threading.Event()
    doc.ModelSpace.items.insert(1, SlowCircle(doc.ModelSpace, gate, entered))
    return gate, entered


# --- the state machine ------------------------------------------------------------------------------------------

def test_a_job_moves_from_running_to_one_final_state():
    job = ExportJob("j1", "a.dwg", Path("a.json"), Limits())
    assert job.state == "running"
    job.finish(Path("a.json"))
    assert job.state == "done"
    job.fail("late failure")
    job.mark_cancelled(Path("a.failed.json"))
    assert job.state == "done" and job.reason is None


def test_a_failure_reason_is_one_line():
    job = ExportJob("j1", "a.dwg", Path("a.json"), Limits())
    job.fail("COM error\n  at line 3\n")
    assert job.state == "failed" and job.reason == "COM error | at line 3"


def test_cancel_is_a_request_the_walk_honours():
    job = ExportJob("j1", "a.dwg", Path("a.json"), Limits())
    job.request_cancel()
    assert job.state == "running" and job.cancel_requested


# --- a whole export ---------------------------------------------------------------------------------------------

def test_an_export_writes_one_complete_json_under_the_temp_exports_folder(jobs, folder):
    app, doc, _ = drawing_with_everything()
    started = start(jobs, app, doc)
    assert started["success"] is True and started["state"] in ("running", "done")
    assert started["output_path"] == str(folder / "Supplier-Pump-20261101-100000.json")
    jobs.join(started["job_id"], 10)
    status = jobs.status(started["job_id"])
    assert status["state"] == "done", status
    assert status["result_path"] == started["output_path"]
    data = json.loads(Path(status["result_path"]).read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["complete"] is True
    assert list(folder.iterdir()) == [Path(status["result_path"])]  # no .partial left behind
    spaces = {s["layout"]: s for s in status["progress"]["spaces"]}
    assert spaces["Model"]["read"] == spaces["Model"]["total"] == doc.ModelSpace.Count
    assert spaces["Vista A"] == {"layout": "Vista A", "read": 3, "total": 3}
    assert status["progress"]["entities_read"] == total_entities(doc)
    assert status["elapsed_s"] >= 0 and "entities_per_second" in status
    assert data["export"]["entities_read"] == total_entities(doc)


def test_an_existing_file_is_never_overwritten(jobs, folder):
    folder.mkdir(parents=True)
    taken = folder / "Supplier-Pump-20261101-100000.json"
    taken.write_text("theirs", encoding="utf-8")
    app, doc, _ = drawing_with_everything()
    started = start(jobs, app, doc)
    jobs.join(started["job_id"], 10)
    assert started["output_path"] == str(folder / "Supplier-Pump-20261101-100000-2.json")
    assert taken.read_text(encoding="utf-8") == "theirs"
    second = start(jobs, app, doc)
    jobs.join(second["job_id"], 10)
    assert second["output_path"].endswith("-3.json")


@pytest.mark.parametrize("limits, words", [
    (dict(max_entities=5), "max_entities 5"),
    (dict(max_bytes=2000), "max_bytes 2000"),
])
def test_a_limit_fails_the_job_with_its_reason_and_never_truncates(jobs, folder, limits, words):
    app, doc, _ = drawing_with_everything()
    started = start(jobs, app, doc, **limits)
    jobs.join(started["job_id"], 10)
    status = jobs.status(started["job_id"])
    assert status["state"] == "failed" and words in status["reason"], status
    assert not Path(started["output_path"]).exists()
    failed = Path(status["result_path"])
    assert failed.name == "Supplier-Pump-20261101-100000.failed.json"
    kept = json.loads(failed.read_text(encoding="utf-8"))
    assert kept["complete"] is False and kept["state"] == "failed" and words in kept["reason"]
    assert [p.name for p in folder.iterdir()] == [failed.name]


def test_the_time_limit_fails_the_job(tmp_path):
    ticks = iter(range(10 ** 6))
    jobs = ExportJobs(temp=TempFolder(base=tmp_path), now=lambda: NOW, clock=lambda: float(next(ticks)))
    app, doc, _ = drawing_with_everything()
    started = start(jobs, app, doc, max_seconds=5)
    jobs.join(started["job_id"], 10)
    status = jobs.status(started["job_id"])
    assert status["state"] == "failed" and "max_seconds 5" in status["reason"]


def test_cancel_ends_the_job_as_cancelled_and_keeps_a_failed_file(jobs, folder):
    app, doc, _ = drawing_with_everything()
    gate, entered = with_slow_circle(doc)
    started = start(jobs, app, doc)
    assert entered.wait(10)
    assert jobs.status(started["job_id"])["state"] == "running"
    answer = jobs.cancel(started["job_id"])
    assert answer["success"] is True and answer["state"] == "running" and answer["cancel_requested"] is True
    gate.set()
    jobs.join(started["job_id"], 10)
    status = jobs.status(started["job_id"])
    assert status["state"] == "cancelled" and "cancel" in status["reason"]
    kept = json.loads(Path(status["result_path"]).read_text(encoding="utf-8"))
    assert kept["state"] == "cancelled" and status["result_path"].endswith(".failed.json")
    assert jobs.cancel(started["job_id"])["state"] == "cancelled"  # already over: unchanged


def test_one_export_at_a_time(jobs):
    app, doc, _ = drawing_with_everything()
    gate, entered = with_slow_circle(doc)
    first = start(jobs, app, doc)
    assert entered.wait(10)
    second = start(jobs, app, doc)
    assert "already running" in second["error"] and second["job_id"] == first["job_id"]
    gate.set()
    jobs.join(first["job_id"], 10)


def test_an_autocad_busy_beyond_patience_fails_the_job(jobs):
    class Rejecting(FakeEntity):
        @property
        def Radius(self):
            raise pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)

    app, doc, _ = drawing_with_everything()
    doc.ModelSpace.items.insert(0, Rejecting(doc.ModelSpace, "AcDbCircle", "0", Center=(0.0, 0.0, 0.0),
                                             Normal=(0.0, 0.0, 1.0)))
    started = start(jobs, app, doc, busy_patience=0)
    jobs.join(started["job_id"], 10)
    status = jobs.status(started["job_id"])
    assert status["state"] == "failed" and "busy" in status["reason"]


def test_an_unknown_job_is_reported(jobs):
    assert jobs.status("nope") == {"error": "Unknown export job: nope"}
    assert jobs.cancel("nope") == {"error": "Unknown export job: nope"}


# --- through the server ------------------------------------------------------------------------------------------

@pytest.fixture
def served(acad, app, jobs):
    acad.exports = jobs
    return acad


def test_export_drawing_answers_at_once_while_the_walk_runs(served, app):
    doc = app.ActiveDocument
    doc.ModelSpace.add("AcDbLine", StartPoint=(0.0, 0.0, 0.0), EndPoint=(1.0, 0.0, 0.0))
    gate, entered = with_slow_circle(doc)
    started = served.export_drawing()
    assert started["success"] is True and started["state"] == "running" and started["document"] == "X-C3D.dwg"
    assert served.get_export_status(started["job_id"])["state"] == "running"
    gate.set()
    served.exports.join(started["job_id"], 10)
    assert served.get_export_status(started["job_id"])["state"] == "done"


def test_a_named_open_drawing_is_exported(served, app):
    other = FakeDocument(name="Other.dwg")
    app.open(other)  # now the active one
    started = served.export_drawing(document="x-c3d.dwg")
    served.exports.join(started["job_id"], 10)
    assert started["document"] == "X-C3D.dwg"
    data = json.loads(Path(served.get_export_status(started["job_id"])["result_path"]).read_text(encoding="utf-8"))
    assert data["drawing"]["name"] == "X-C3D.dwg"


def test_a_drawing_that_is_not_open_is_refused_with_the_open_ones(served):
    result = served.export_drawing(document="Missing.dwg")
    assert "Missing.dwg" in result["error"] and result["open_documents"] == ["X-C3D.dwg"]


def test_no_drawing_open_says_so(served, app):
    app.Documents.docs.clear()
    app.ActiveDocument = None
    assert served.export_drawing()["error"].startswith("No drawing is open in AutoCAD")
    assert app.Documents.added == 0


def test_a_finished_job_keeps_the_exports_folder_at_three(jobs, folder):
    """Known gap 16: the rule also holds in a long-running server, not only at its next start."""
    app, doc, _ = drawing_with_everything()
    paths = []
    for _ in range(4):
        started = start(jobs, app, doc)
        jobs.join(started["job_id"], 10)
        paths.append(Path(started["output_path"]))
    assert [p.exists() for p in paths] == [False, True, True, True]


def test_the_tool_says_how_long_exports_are_kept(acad):
    import asyncio
    import mcp.types as types
    acad.setup_tools()
    handler = acad.server.request_handlers[types.ListToolsRequest]
    tools = {t.name: t for t in asyncio.run(handler(types.ListToolsRequest(method="tools/list"))).root.tools}
    description = tools["export_drawing"].description
    assert "last 3 exports" in description and "7 days" in description and "newest" in description



# --- QA-6 / SEC-6: a hostile drawing name still writes inside exports\ ---------------------------------------

HOSTILE = [r"..\..\evil.dwg", r"C:\Windows\System32\evil.dwg", r"\\server\share\evil.dwg", "evil.dwg:hidden",
           "evil.dwg::$DATA", "evil\n.dwg", "CON", "CON.dwg", "nul.dwg", "..", "", "a/b/../../c.dwg", " . "]


@pytest.mark.parametrize("name", HOSTILE)
def test_a_hostile_drawing_name_still_writes_inside_exports(tmp_path, name):
    folder = tmp_path / "exports"
    folder.mkdir()
    final, failed, partial = reserve(folder, name, NOW)
    inside = os.path.realpath(folder) + os.sep
    for path in (final, failed, partial):
        assert path.parent == folder and os.path.realpath(path).startswith(inside), path
        assert not set(path.name) & set(':\n\\/'), path.name
        # always "<stem>-<timestamp>.<ext>": never a bare device name (CON, NUL) nor a stream
        assert re.fullmatch(r"[^:\\/\n]+-20261101-100000\.(json|failed\.json|json\.partial)", path.name), path.name
    assert list(folder.iterdir()) == [partial]


def test_a_hostile_drawing_name_exports_inside_the_folder(jobs, folder):
    app, doc, _ = drawing_with_everything()
    doc.Name = r"..\..\evil.dwg"
    started = start(jobs, app, doc)
    jobs.join(started["job_id"], 10)
    status = jobs.status(started["job_id"])
    assert status["state"] == "done", status
    assert Path(status["result_path"]).parent == folder and Path(status["result_path"]).name.startswith("evil-")


# --- QA-4: the marshalled COM stream is released on every path ------------------------------------------------

class CountingOpener:
    made = []

    def __init__(self, app):
        self.app, self.used, self.released = app, 0, 0
        CountingOpener.made.append(self)

    def __call__(self):
        self.used += 1
        return self.app

    def release(self):
        self.released += 1


@pytest.fixture
def openers(monkeypatch):
    CountingOpener.made = []
    monkeypatch.setattr(export_module, "app_opener", CountingOpener)
    return CountingOpener.made


def test_a_refused_export_marshals_nothing(jobs, openers):
    app, doc, _ = drawing_with_everything()
    gate, entered = with_slow_circle(doc)
    first = start(jobs, app, doc)
    assert entered.wait(10)
    assert "already running" in start(jobs, app, doc)["error"]
    gate.set()
    jobs.join(first["job_id"], 10)
    assert len(openers) == 1 and openers[0].used == 1  # the refused call marshalled no stream


def test_a_thread_that_cannot_start_releases_the_stream(jobs, openers, folder, monkeypatch):
    def refuse(self):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, "start", refuse)
    app, doc, _ = drawing_with_everything()
    result = start(jobs, app, doc)
    assert "can't start new thread" in result["error"]
    assert [(o.used, o.released) for o in openers] == [(0, 1)]
    assert not any(p.name.endswith(".partial") for p in folder.iterdir())
    assert all(j.state != "running" for j in jobs.jobs.values())


def test_the_real_opener_releases_its_stream_without_a_thread():
    import win32com.client
    d = win32com.client.Dispatch("Scripting.Dictionary")
    opener = export_module.app_opener(d)
    opener.release()
    assert opener.stream is None
    opener.release()  # twice is harmless
    with pytest.raises(RuntimeError):
        opener()


# --- QA-8: a long drawing name stays under Windows' 260-character path -----------------------------------------

LONG_A = "Supplier-" + "A" * 280 + ".dwg"  # 300 characters with the prefix and extension
LONG_B = "Supplier-" + "A" * 279 + "B.dwg"  # the same first 288 characters


def test_a_300_character_name_gives_a_short_readable_stem_with_a_hash():
    stem = export_module.safe_stem(LONG_A)
    assert len(stem) <= export_module.MAX_STEM == 80
    assert stem.startswith("Supplier-AAAA") and re.fullmatch(r".+~[0-9a-f]{8}", stem)
    assert export_module.safe_stem(LONG_B) != stem  # two long names never collide
    assert export_module.safe_stem(LONG_A) == stem  # and the same name gives the same stem
    assert export_module.safe_stem("Supplier-Pump.dwg") == "Supplier-Pump"  # short names unchanged


def test_the_export_path_of_a_300_character_name_fits_under_the_real_temp_folder():
    final_name = f"{export_module.safe_stem(LONG_A)}-20261101-100000-99.failed.json"
    path = TempFolder().root / "exports" / final_name  # the real %TEMP%, as the server uses it
    assert len(str(path)) < 260, len(str(path))


def test_a_300_character_drawing_name_exports(jobs, folder):
    app, doc, _ = drawing_with_everything()
    doc.Name = LONG_A
    first = start(jobs, app, doc)
    assert first.get("success"), first
    jobs.join(first["job_id"], 10)
    assert jobs.status(first["job_id"])["state"] == "done"
    second = start(jobs, app, doc)  # same name, same second: never overwritten
    jobs.join(second["job_id"], 10)
    assert second["output_path"] != first["output_path"] and second["output_path"].endswith("-2.json")
    assert Path(first["output_path"]).exists() and Path(second["output_path"]).exists()
