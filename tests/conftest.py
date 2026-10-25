import pytest

from autocad_mcp import server as server_module
from autocad_mcp.server import AutoCADCOMServer
from fake_acad import FakeApp


@pytest.fixture
def app():
    return FakeApp()


@pytest.fixture
def acad(app, monkeypatch):
    """An AutoCADCOMServer whose COM lookup finds the fake AutoCAD, with no delay between calls."""
    monkeypatch.setattr(server_module, "ACAD_PROGID", "AutoCAD.Application.26")
    monkeypatch.setattr(server_module, "OP_DELAY", 0)
    monkeypatch.setattr(server_module.win32com.client, "GetActiveObject",
                        lambda progid: app if progid == "AutoCAD.Application.26" else None)
    return AutoCADCOMServer()
