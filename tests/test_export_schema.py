"""docs/concepts/export-schema.md: what export_drawing writes, read from a fake drawing with one of everything.

The walk itself (read_drawing) runs here on the calling thread; the background job around it is pinned in
test_export_jobs.py."""
import copy
import json
import math

import pytest

from autocad_mcp.export import SCHEMA, SCHEMA_VERSION, Limits, read_drawing
from export_drawing_fake import drawing_with_everything, total_entities


@pytest.fixture(scope="module")
def exported():
    app, doc, h = drawing_with_everything()
    return read_drawing(app, doc, Limits(block_depth=4)), doc, h


def entity(data, handle):
    found = [e for e in data["entities"] if e["handle"] == handle]
    assert len(found) == 1, handle
    return found[0]


def test_the_file_names_its_schema_and_version(exported):
    data, _, _ = exported
    assert data["schema"] == SCHEMA == "cemengal.autocad.export"
    assert data["schema_version"] == SCHEMA_VERSION == 1
    assert data["complete"] is True
    json.dumps(data)  # JSON-able as it stands


def test_the_drawing_header(exported):
    data, _, _ = exported
    d = data["drawing"]
    assert d["name"] == "Supplier-Pump.dwg" and d["full_path"] == "D:\\drawings\\Supplier-Pump.dwg"
    assert d["version"] == "26.0s (LMS Tech)"
    assert data["application"]["name"] == "Autodesk Civil 3D 2027"
    assert (d["insunits"], d["insunits_name"]) == (4, "Millimeters")
    assert (d["measurement"], d["measurement_name"]) == (1, "metric")
    assert [(s["layout"], s["is_model"], s["block"]) for s in d["spaces"]] == [
        ("Model", True, "*Model_Space"), ("Vista A", False, "*Paper_Space"), ("Vista Z", False, "*Paper_Space0")]


def test_layouts_and_their_viewports(exported):
    data, _, h = exported
    layouts = {l["name"]: l for l in data["layouts"]}
    assert layouts["Model"]["is_model"] is True and layouts["Model"]["viewports"] == []
    sheet = layouts["Vista A"]
    assert sheet["is_model"] is False and sheet["tab_order"] == 1 and sheet["entity_count"] == 3
    (vp,) = sheet["viewports"]
    assert vp["handle"] == h["viewport"]
    assert vp["center"] == [148.5, 105.0, 0.0] and (vp["width"], vp["height"]) == (250.0, 180.0)
    assert vp["target"] == [0.0, 0.0, 0.0] and vp["direction"] == [0.0, 0.0, 1.0]
    assert vp["custom_scale"] == 0.02
    # not in ActiveX's IAcadPViewport: reported, never invented
    assert vp["view_center"] is None and vp["frozen_layers"] is None
    assert {"view_center", "frozen_layers"} <= set(vp["unavailable"])
    assert layouts["Vista Z"]["entity_count"] == 0


def test_every_entity_names_its_type_handle_layer_space_and_layout(exported):
    data, _, h = exported
    for e in data["entities"]:
        assert {"type", "object_name", "handle", "layer", "space", "layout"} <= set(e), e
    assert (entity(data, h["line"])["space"], entity(data, h["line"])["layout"]) == ("model", "Model")
    sheet_text = entity(data, h["sheet_text"])
    assert (sheet_text["space"], sheet_text["layout"]) == ("paper", "Vista A")


def test_geometry(exported):
    data, _, h = exported
    line = entity(data, h["line"])
    assert line["type"] == "line" and line["start"] == [0.0, 0.0, 0.0] and line["end"] == [100.0, 0.0, 0.0]
    lw = entity(data, h["lwpoly"])
    assert lw["type"] == "polyline" and lw["closed"] is True
    assert lw["vertices"] == [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0]] and lw["bulges"] == [0.0, 1.0, 0.0]
    p2 = entity(data, h["poly2d"])
    assert p2["type"] == "polyline2d" and p2["vertices"] == [[0.0, 0.0, 0.0], [5.0, 5.0, 0.0]]
    assert p2["bulges"] == [0.5, 0.0]
    p3 = entity(data, h["poly3d"])
    assert p3["type"] == "polyline3d" and p3["vertices"] == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]
    arc = entity(data, h["arc"])
    assert arc["center"] == [5.0, 5.0, 0.0] and arc["radius"] == 2.0 and arc["end_angle"] == math.pi / 2
    assert entity(data, h["circle"])["radius"] == 0.5
    ellipse = entity(data, h["ellipse"])
    assert ellipse["major_axis"] == [4.0, 0.0, 0.0] and ellipse["radius_ratio"] == 0.5


def test_splines_keep_their_exact_definition(exported):
    data, _, h = exported
    s = entity(data, h["spline"])
    assert s["type"] == "spline" and s["degree"] == 3 and s["rational"] is False
    assert s["control_points"] == [[0.0, 0.0, 0.0], [1.0, 1.0, 0.0], [2.0, 0.0, 0.0], [3.0, 1.0, 0.0]]
    assert s["knots"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    assert s["weights"] is None and s["fit_points"] == []


def test_text_and_mtext_keep_raw_and_plain(exported):
    data, _, h = exported
    t = entity(data, h["text"])
    assert t["type"] == "text" and t["raw"] == "%%c50 VISTA A" and t["plain"] == "Ø50 VISTA A"
    assert t["position"] == [0.0, 50.0, 0.0] and t["height"] == 3.5 and t["rotation"] == 0.0
    assert t["style"] == "Standard"
    m = entity(data, h["mtext"])
    assert m["type"] == "mtext" and m["raw"] == r"{\H2.5;Vista Z}\PNozzle N1" and m["plain"] == "Vista Z\nNozzle N1"
    assert m["style"] == "ISO" and m["width"] == 40.0


def test_leaders_and_multileaders_keep_text_and_points(exported):
    data, _, h = exported
    leader = entity(data, h["leader"])
    assert leader["type"] == "leader"
    assert leader["points"] == [[0.0, 0.0, 0.0], [10.0, 10.0, 0.0], [20.0, 10.0, 0.0]]
    assert leader["annotation_handle"] == h["note"] and leader["plain"] == "SEE NOTE 3"
    ml = entity(data, h["mleader"])
    assert ml["type"] == "multileader" and ml["plain"] == "N2\nDN50"
    assert ml["leader_lines"] == [[[0.0, 0.0, 0.0], [5.0, 5.0, 0.0]], [[0.0, 0.0, 0.0], [-5.0, 5.0, 0.0]]]


def test_dimensions_carry_measurement_override_and_displayed_text(exported):
    data, _, h = exported
    d = entity(data, h["dim"])
    assert d["type"] == "dimension" and d["dim_type"] == "rotated"
    assert d["measurement"] == 1499.99999 and d["text_override"] == ""
    assert d["displayed_text"] == "1500" and d["displayed_text_plain"] == "1500"
    assert d["displayed_text_source"] == "computed" and d["displayed_text_approximate"] is False
    assert d["text_position"] == [750.0, 20.0, 0.0]
    # AutoCAD 2025's IAcadDimRotated has no ExtLine1Point / ExtLine2Point (type info, live 2026-11-01)
    assert d["points"] == {}
    assert {"ext_line1_point", "ext_line2_point", "dimension_line_points"} <= set(d["unavailable"])
    assert d["style"]["name"] == "CEM-ISO" and d["style"]["precision"] == 0 and d["style"]["units_format"] == 2
    assert d["style"]["alt_units"] is None
    over = entity(data, h["dim_override"])
    assert over["dim_type"] == "aligned" and over["displayed_text"] == "812 TYP."
    assert over["points"] == {"ext_line1_point": [0.0, 0.0, 0.0], "ext_line2_point": [812.0, 0.0, 0.0]}
    radial = entity(data, h["dim_radial"])
    assert radial["dim_type"] == "radial" and radial["displayed_text_plain"] == "R25"
    assert {"center_point", "chord_point"} <= set(radial["unavailable"])
    angular = entity(data, h["dim_angular"])
    assert angular["dim_type"] == "angular" and angular["displayed_text_plain"] == "45°"
    assert angular["points"]["ext_line2_end_point"] == [1.0, 1.0, 0.0]
    assert entity(data, h["sheet_dim"])["displayed_text"] == "30"


def test_inserts_and_attributes(exported):
    data, _, h = exported
    ins = entity(data, h["insert"])
    assert ins["type"] == "insert" and ins["name"] == "PUMP" and ins["effective_name"] == "PUMP"
    assert ins["position"] == [200.0, 0.0, 0.0] and ins["scale"] == [2.0, 2.0, 1.0]
    assert ins["rotation"] == math.pi / 2
    assert ins["attributes"] == [{"tag": "TAG", "value": "P-101A"}]


def test_referenced_block_definitions_once_each_without_recursing_forever(exported):
    data, _, _ = exported
    blocks = data["blocks"]
    assert set(blocks) == {"PUMP", "NOZZLE", "BOLT", "SITE-XREF"}
    pump = blocks["PUMP"]
    assert pump["depth"] == 1 and pump["origin"] == [0.0, 0.0, 0.0]
    assert [e["type"] for e in pump["entities"]] == ["circle", "attribute_definition", "insert"]
    assert pump["entities"][1]["tag"] == "TAG" and pump["entities"][1]["default"] == "P-101"
    assert pump["entities"][0]["space"] == "block" and pump["entities"][0]["block"] == "PUMP"
    assert blocks["NOZZLE"]["depth"] == 2 and blocks["BOLT"]["depth"] == 3
    assert len(blocks["BOLT"]["entities"]) == 2  # BOLT inside BOLT is read once, not followed again
    xref = blocks["SITE-XREF"]
    assert xref["is_xref"] is True and xref["entities"] == [] and xref["path"] == "..\\site.dwg"
    assert "external reference" in xref["skipped"]


def test_the_block_depth_limit_is_reported_not_silent():
    app, doc, _ = drawing_with_everything()
    data = read_drawing(app, doc, Limits(block_depth=1))
    assert set(data["blocks"]) == {"PUMP", "SITE-XREF"}
    assert {"block": "NOZZLE", "depth": 2, "reason": "block_depth limit 1"} in data["blocks_not_read"]


def test_counts_cover_every_entity_read_or_skipped_with_its_reason(exported):
    data, doc, h = exported
    counts = data["counts"]
    by_type = counts["by_type"]
    assert by_type["AcDbLine"]["read"] == 2  # model space + NOZZLE
    assert by_type["AeccDbPipe"] == {"read": 0, "skipped": 1, "failed": 0, "with_errors": 0}
    assert "not exported" in counts["skipped_reasons"]["AeccDbPipe"]
    assert by_type["AcDbHatch"]["skipped"] == 1 and "hatch" in counts["skipped_reasons"]["AcDbHatch"].lower()
    seen = sum(c["read"] + c["skipped"] + c["failed"] for c in by_type.values())
    assert seen == total_entities(doc) == counts["total"]["read"] + counts["total"]["skipped"] + counts["total"]["failed"]
    # a skipped entity is still listed, with its reason
    pipe = entity(data, h["pipe"])
    assert pipe["type"] == "other" and "not exported" in pipe["skipped"]


def test_a_property_the_object_lacks_is_marked_not_fatal(exported):
    data, _, h = exported
    broken = entity(data, h["broken"])
    assert broken["center"] is None and "center" in broken["unavailable"] and broken["radius"] == 3.0
    assert data["counts"]["by_type"]["AcDbCircle"]["read"] == 4


def test_the_export_does_not_modify_the_drawing():
    app, doc, _ = drawing_with_everything()
    blocks = [b for b in doc.Blocks.items]
    before = [[copy.copy(e.__dict__) for e in b.items] for b in blocks]
    read_drawing(app, doc, Limits())
    assert [[e.__dict__ for e in b.items] for b in blocks] == before
    assert doc.writes == [] and doc.commands == [] and doc.regens == 0 and doc.Saved is True
    assert doc.Layers.added == [] and app.Documents.added == 0
    assert all(e.updates == 0 for b in blocks for e in b.items)
