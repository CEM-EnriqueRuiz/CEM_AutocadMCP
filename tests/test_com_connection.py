"""docs/decisions/0002: ProgID discovery and the lazy connection."""
import winreg
from contextlib import contextmanager

import pythoncom

from autocad_mcp import server as server_module
from autocad_mcp.server import AutoCADCOMServer


def fake_registry(monkeypatch, keys):
    @contextmanager
    def open_key(root, path):
        yield root

    def enum_key(root, i):
        if i >= len(keys):
            raise OSError("no more")
        return keys[i]

    monkeypatch.setattr(winreg, "OpenKey", open_key)
    monkeypatch.setattr(winreg, "EnumKey", enum_key)


def test_generic_progid_first_then_every_versioned_one_newest_first(monkeypatch):
    monkeypatch.setattr(server_module, "ACAD_PROGID", "")
    fake_registry(monkeypatch, ["AutoCAD.Application", "AutoCAD.Application.23", "AutoCAD.Application.26",
                                "AutoCAD.Drawing.26", "AutoCAD.Application.25.1", "AutoCAD.Application.24"])
    assert AutoCADCOMServer.candidate_progids() == [
        "AutoCAD.Application", "AutoCAD.Application.26", "AutoCAD.Application.25.1",
        "AutoCAD.Application.24", "AutoCAD.Application.23"]


def test_acad_progid_forces_one(monkeypatch):
    monkeypatch.setattr(server_module, "ACAD_PROGID", "AutoCAD.Application.26")
    assert AutoCADCOMServer.candidate_progids() == ["AutoCAD.Application.26"]


def test_falls_through_a_stale_generic_progid(monkeypatch, app):
    """The generic ProgID can point at an uninstalled release (CurVer 23 on the main machine)."""
    monkeypatch.setattr(server_module, "ACAD_PROGID", "")
    fake_registry(monkeypatch, ["AutoCAD.Application.23", "AutoCAD.Application.26"])

    def get_active(progid):
        if progid == "AutoCAD.Application.26":
            return app
        raise Exception("Operation unavailable")

    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject", get_active)
    acad = AutoCADCOMServer()
    assert acad.connect_to_autocad()
    assert acad.progid == "AutoCAD.Application.26"


def test_no_running_autocad_is_an_error_not_a_launch(monkeypatch):
    monkeypatch.setattr(server_module, "ACAD_PROGID", "AutoCAD.Application.26")
    monkeypatch.setattr(server_module, "ACAD_AUTOSTART", False)

    def get_active(progid):
        raise Exception("Operation unavailable")

    def dispatch(progid):
        raise AssertionError("launched AutoCAD without ACAD_AUTOSTART=1")

    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject", get_active)
    monkeypatch.setattr(server_module.win32com.client, "Dispatch", dispatch)
    result = AutoCADCOMServer().get_drawing_info()
    assert "Not connected to AutoCAD" in result["error"]
    assert "Operation unavailable" in result["error"]


def test_a_busy_autocad_is_retried(acad, monkeypatch):
    monkeypatch.setattr(server_module.time, "sleep", lambda s: None)
    calls = []

    def busy_twice():
        calls.append(1)
        if len(calls) < 3:
            raise pythoncom.com_error(server_module.RPC_E_CALL_REJECTED, "Call was rejected by callee.", None, None)
        return "done"

    assert acad.safe_operation(busy_twice) == "done"
    assert len(calls) == 3


def test_the_server_follows_the_active_drawing(acad, app):
    from fake_acad import FakeDocument
    acad.get_drawing_info()
    other = FakeDocument(name="Other.dwg")
    app.ActiveDocument = other
    assert acad.get_drawing_info()["filename"] == "Other.dwg"
