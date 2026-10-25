"""docs/decisions/0005: every tool call ends inside the host's 60 s, even on a large drawing.

Measured on 2026-10-24 on a Civil 3D 2027 drawing (6,947 layers, 958 entities): ~45 ms per layer read,
~65 ms per entity read, 1.7-3 s per Regen. Listing every layer took ~5 minutes, so get_drawing_info
timed out; a Regen after every created line made a thick rectangle take ~30-50 s."""
from autocad_mcp import server as server_module
from fake_acad import FakeApp, FakeDocument


def big_drawing(app, layers):
    app.ActiveDocument = FakeDocument(layers=["0"] + [f"L{i}" for i in range(layers - 1)])
    app.Documents.docs = [app.ActiveDocument]
    return app.ActiveDocument


def test_drawing_info_lists_at_most_100_layers_by_default(acad, app):
    big_drawing(app, 300)
    info = acad.get_drawing_info()
    assert info["total_layers"] == 300
    assert len(info["available_layers"]) == 100
    assert info["layers_truncated"] is True


def test_drawing_info_takes_a_layer_limit(acad, app):
    big_drawing(app, 300)
    info = acad.get_drawing_info(max_layers=500)
    assert len(info["available_layers"]) == 300
    assert info["layers_truncated"] is False


def test_drawing_info_stops_listing_layers_at_the_time_budget(acad, app, monkeypatch):
    big_drawing(app, 50)
    monkeypatch.setattr(server_module, "TOOL_BUDGET", 0)
    info = acad.get_drawing_info()
    assert info["available_layers"] == [] and info["layers_truncated"] is True
    assert info["total_layers"] == 50 and info["filename"] == "X-C3D.dwg"


def test_get_entities_stops_at_the_time_budget(acad, app, monkeypatch):
    for i in range(5):
        acad.create_line([i, 0], [i, 1])
    monkeypatch.setattr(server_module, "TOOL_BUDGET", 0)
    result = acad.get_entities()
    assert result["total_count"] == 5 and result["returned_count"] == 0
    assert result["truncated"] is True


def test_get_entities_says_when_it_is_complete(acad):
    acad.create_line([0, 0], [1, 1])
    assert acad.get_entities()["truncated"] is False


def test_creating_entities_redraws_them_without_a_regen(acad, app):
    acad.create_line([0, 0], [10, 0], thickness=0.5)
    acad.create_circle([0, 0], 2, thickness=0.2)
    acad.create_arc([0, 0], 3, 0, 90, thickness=0.2)
    acad.create_text([0, 0], "t")
    acad.create_rectangle([0, 0], [2, 2], thickness=0.1)
    doc = app.ActiveDocument
    assert doc.regens == 0
    assert all(e.updates == 1 for e in doc.ModelSpace.items)


def test_delete_by_handles_looks_each_handle_up_without_scanning(acad, app):
    handles = acad.create_line([0, 0], [10, 0], thickness=0.5)["handles"]
    keep = acad.create_circle([0, 0], 1)["handles"]
    space = app.ActiveDocument.ModelSpace
    space.item_calls = 0
    result = acad.delete_entities_by_handles([h.lower() for h in handles] + ["FFFF"])
    assert result["deleted_count"] == 4 and result["not_found"] == ["FFFF"]
    assert space.item_calls == 0
    assert [e.Handle for e in space.items] == keep


def test_delete_by_handles_never_deletes_what_is_not_in_model_space(acad, app):
    layer = app.ActiveDocument.Layers.Item("C-ROAD")
    result = acad.delete_entities_by_handles([layer.Handle])
    assert result["deleted_count"] == 0 and result["not_found"] == [layer.Handle]
