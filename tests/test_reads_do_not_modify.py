"""docs/decisions/0004: a read never modifies the drawing; a write creates only the layer it needs."""


def test_reading_the_drawing_adds_no_layer(acad, app):
    layers = app.ActiveDocument.Layers
    info = acad.get_drawing_info()
    acad.get_entities(max_entities=10)
    assert info["filename"] == "X-C3D.dwg"
    assert layers.added == []
    assert info["total_layers"] == 2


def test_a_structure_creates_only_its_own_layer(acad, app):
    result = acad.create_structure("wall", {"start": [0, 0], "end": [5, 0]})
    assert result["success"] and result["layer"] == "WALLS"
    assert app.ActiveDocument.Layers.added == ["WALLS"]
    assert {e.Layer for e in app.ActiveDocument.ModelSpace.items} == {"WALLS"}


def test_a_label_also_creates_the_annotation_layer(acad, app):
    acad.create_structure("door", {"start": [0, 0], "end": [1, 0]}, label="D1")
    assert app.ActiveDocument.Layers.added == ["DOORS", "ANNOTATION"]
    text = [e for e in app.ActiveDocument.ModelSpace.items if e.ObjectName == "AcDbText"]
    assert [t.Layer for t in text] == ["ANNOTATION"]


def test_a_structure_restores_the_current_layer(acad, app):
    acad.create_structure("furniture", {"center": [1, 1], "radius": 0.5})
    assert app.ActiveDocument.ActiveLayer.Name == "0"


def test_basic_entities_go_on_the_current_layer_and_add_no_layer(acad, app):
    acad.create_line([0, 0], [1, 1])
    acad.create_circle([0, 0], 1)
    acad.create_text([0, 0], "t")
    assert app.ActiveDocument.Layers.added == []
    assert {e.Layer for e in app.ActiveDocument.ModelSpace.items} == {"0"}
