"""docs/decisions/0002: a busy AutoCAD is retried, also when pywin32 reports it as an AttributeError.

Seen live on 2026-10-24 right after launching plain AutoCAD 2027 and during Documents.Open: GetActiveObject
succeeded, then `.Name` raised AttributeError('AutoCAD.Application.26.Name'), because pywin32's late binding
swallows the rejected GetIDsOfNames. Only that race is retried, within the same budget as RPC_E_CALL_REJECTED;
a property that does not exist fails at once."""
import pytest

from autocad_mcp import server as server_module
from autocad_mcp.server import AutoCADCOMServer
from fake_acad import FakeApp, RacyDispatch


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(server_module.time, "sleep", lambda s: None)
    monkeypatch.setattr(server_module, "ACAD_PROGID", "AutoCAD.Application.26")
    monkeypatch.setattr(server_module, "OP_DELAY", 0)


def serve(monkeypatch, app):
    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject", lambda progid: app)
    return AutoCADCOMServer()


def test_the_startup_race_is_retried_while_connecting(no_wait, monkeypatch):
    app = RacyDispatch(FakeApp(), busy_for=3)
    info = serve(monkeypatch, app).get_drawing_info()
    assert "error" not in info, info
    assert info["filename"] == "X-C3D.dwg"


def test_safe_operation_retries_the_race(no_wait, monkeypatch):
    app = RacyDispatch(FakeApp(), busy_for=2)
    acad = serve(monkeypatch, app)
    assert acad.safe_operation(lambda: app.Name) == "Autodesk Civil 3D 2027"
    assert app.lookups == 3


def test_a_property_that_does_not_exist_is_not_retried(no_wait, monkeypatch):
    app = RacyDispatch(FakeApp(), busy_for=0)
    acad = serve(monkeypatch, app)
    assert acad.safe_operation(lambda: app.NoSuchProperty) is None
    assert app.lookups == 1
    assert "NoSuchProperty" in acad.last_error


def test_a_plain_python_attribute_error_is_not_retried(no_wait, monkeypatch, app):
    acad = serve(monkeypatch, app)
    calls = []

    def bug():
        calls.append(1)
        return None.Handle

    assert acad.safe_operation(bug) is None
    assert len(calls) == 1


def test_the_race_retry_is_bounded(no_wait, monkeypatch):
    app = RacyDispatch(FakeApp(), busy_for=10_000)
    acad = serve(monkeypatch, app)
    result = acad.get_drawing_info()
    assert "stayed busy" in result["error"]
    assert app.lookups <= 2 * server_module.BUSY_RETRIES  # connect, then the reconnect of the same call
