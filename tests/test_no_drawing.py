"""docs/decisions/0004: no tool creates a drawing the user did not ask for.

Plain AutoCAD 2027 starts on its Start tab with no document (seen live on 2026-10-24); the user's original
connect_to_autocad then called Documents.Add(), so the first tool call, even a read, opened a blank drawing.
Now every tool answers that no drawing is open, so the agent can ask the user."""
import pytest

from autocad_mcp import server as server_module
from autocad_mcp.server import AutoCADCOMServer
from fake_acad import FakeApp, FakeDocument


@pytest.fixture
def start_tab(monkeypatch):
    app = FakeApp(empty=True)
    monkeypatch.setattr(server_module, "ACAD_PROGID", "AutoCAD.Application.26")
    monkeypatch.setattr(server_module, "OP_DELAY", 0)
    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject", lambda progid: app)
    return app, AutoCADCOMServer()


def test_a_read_on_the_start_tab_says_no_drawing_is_open(start_tab):
    app, acad = start_tab
    result = acad.get_drawing_info()
    assert result["error"].startswith("No drawing is open in AutoCAD")
    assert app.Documents.added == 0


@pytest.mark.parametrize("call", [
    lambda a: a.get_entities(),
    lambda a: a.create_line([0, 0], [1, 1]),
    lambda a: a.create_structure("wall", {"start": [0, 0], "end": [1, 0]}),
    lambda a: a.delete_entities_by_handles(["1F"]),
    lambda a: a.zoom_extents(),
])
def test_no_tool_creates_a_drawing(start_tab, call):
    app, acad = start_tab
    result = call(acad)
    assert result["error"].startswith("No drawing is open in AutoCAD")
    assert app.Documents.added == 0 and app.Documents.Count == 0


def test_a_drawing_the_user_opens_later_is_found(start_tab):
    app, acad = start_tab
    acad.get_drawing_info()
    app.open(FakeDocument(name="Opened.dwg"))
    assert acad.get_drawing_info()["filename"] == "Opened.dwg"


def test_closing_the_last_drawing_is_reported_the_same_way(monkeypatch, acad, app):
    acad.get_drawing_info()
    app.Documents.docs.clear()
    app.ActiveDocument = None
    assert acad.create_line([0, 0], [1, 1])["error"].startswith("No drawing is open in AutoCAD")
    assert app.Documents.added == 0
