"""A fake drawing with one of everything the export reads (docs/concepts/export-schema.md), built on fake_acad.

Property names are AutoCAD's ActiveX names; a property a real interface lacks is simply absent here too
(for example a viewport's view centre), so the export must report it as unavailable."""
import math

from fake_acad import FakeApp, FakeDocument

DIM_FORMAT = dict(UnitsFormat=2, PrimaryUnitsPrecision=0, LinearScaleFactor=1.0, RoundDistance=0.0,
                  SuppressLeadingZeros=False, SuppressTrailingZeros=False, DecimalSeparator=".",
                  TextPrefix="", TextSuffix="", AltUnits=False, ToleranceDisplay=0,
                  StyleName="CEM-ISO", TextRotation=0.0)


def drawing_with_everything():
    """Returns (app, doc, handles): handles names the entities the tests look at."""
    doc = FakeDocument(name="Supplier-Pump.dwg", layers=("0", "GEOM", "DIM", "TEXT"))
    ms, h = doc.ModelSpace, {}
    h["line"] = ms.add("AcDbLine", "GEOM", StartPoint=(0.0, 0.0, 0.0), EndPoint=(100.0, 0.0, 0.0)).Handle
    bulges = [0.0, 1.0, 0.0]
    h["lwpoly"] = ms.add("AcDbPolyline", "GEOM", Coordinates=(0.0, 0.0, 10.0, 0.0, 10.0, 5.0), Closed=True,
                         Elevation=0.0, GetBulge=lambda i: bulges[i]).Handle
    h["poly2d"] = ms.add("AcDb2dPolyline", "GEOM", Coordinates=(0.0, 0.0, 0.0, 5.0, 5.0, 0.0), Closed=False,
                         Type=0, GetBulge=lambda i: 0.5 if i == 0 else 0.0).Handle
    h["poly3d"] = ms.add("AcDb3dPolyline", "GEOM", Coordinates=(0.0, 0.0, 0.0, 1.0, 2.0, 3.0),
                         Closed=False).Handle
    h["arc"] = ms.add("AcDbArc", "GEOM", Center=(5.0, 5.0, 0.0), Radius=2.0, StartAngle=0.0,
                      EndAngle=math.pi / 2, Normal=(0.0, 0.0, 1.0)).Handle
    h["circle"] = ms.add("AcDbCircle", "GEOM", Center=(1.0, 1.0, 0.0), Radius=0.5, Normal=(0.0, 0.0, 1.0)).Handle
    h["ellipse"] = ms.add("AcDbEllipse", "GEOM", Center=(0.0, 0.0, 0.0), MajorAxis=(4.0, 0.0, 0.0),
                          RadiusRatio=0.5, StartAngle=0.0, EndAngle=2 * math.pi, Normal=(0.0, 0.0, 1.0)).Handle
    h["spline"] = ms.add("AcDbSpline", "GEOM", Degree=3, Closed=False, IsRational=False,
                         ControlPoints=(0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 2.0, 0.0, 0.0, 3.0, 1.0, 0.0),
                         Knots=(0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0), NumberOfFitPoints=0).Handle
    h["text"] = ms.add("AcDbText", "TEXT", TextString="%%c50 VISTA A", InsertionPoint=(0.0, 50.0, 0.0),
                       Height=3.5, Rotation=0.0, StyleName="Standard").Handle
    h["mtext"] = ms.add("AcDbMText", "TEXT", TextString=r"{\H2.5;Vista Z}\PNozzle N1",
                        InsertionPoint=(0.0, 60.0, 0.0), Height=2.5, Rotation=0.0, StyleName="ISO",
                        Width=40.0, AttachmentPoint=1).Handle
    note = ms.add("AcDbMText", "TEXT", TextString="SEE NOTE 3", InsertionPoint=(20.0, 20.0, 0.0), Height=2.5,
                  Rotation=0.0, StyleName="ISO", Width=0.0, AttachmentPoint=1)
    h["note"] = note.Handle
    h["leader"] = ms.add("AcDbLeader", "TEXT", Coordinates=(0.0, 0.0, 0.0, 10.0, 10.0, 0.0, 20.0, 10.0, 0.0),
                         Type=1, Annotation=note).Handle
    lines = {0: (0, 1)}
    vertices = {0: (0.0, 0.0, 0.0, 5.0, 5.0, 0.0), 1: (0.0, 0.0, 0.0, -5.0, 5.0, 0.0)}
    h["mleader"] = ms.add("AcDbMLeader", "TEXT", ContentType=2, TextString=r"N2\PDN50", LeaderCount=1,
                          GetLeaderLineIndexes=lambda i: lines[i],
                          GetLeaderLineVertices=lambda j: vertices[j]).Handle
    h["dim"] = ms.add("AcDbRotatedDimension", "DIM", Measurement=1499.99999, TextOverride="",
                      TextPosition=(750.0, 20.0, 0.0), Rotation=0.0, **DIM_FORMAT).Handle  # no ExtLine*Point (live)
    h["dim_override"] = ms.add("AcDbAlignedDimension", "DIM", Measurement=812.0, TextOverride="<> TYP.",
                               TextPosition=(0.0, 0.0, 0.0), ExtLine1Point=(0.0, 0.0, 0.0),
                               ExtLine2Point=(812.0, 0.0, 0.0), **DIM_FORMAT).Handle
    h["dim_radial"] = ms.add("AcDbRadialDimension", "DIM", Measurement=25.0, TextOverride="",
                             TextPosition=(0.0, 0.0, 0.0), **DIM_FORMAT).Handle
    angular = {k: v for k, v in DIM_FORMAT.items() if k not in ("UnitsFormat", "PrimaryUnitsPrecision",
                                                                "LinearScaleFactor", "RoundDistance")}
    h["dim_angular"] = ms.add("AcDb2LineAngularDimension", "DIM", Measurement=math.pi / 4, TextOverride="",
                              TextPosition=(0.0, 0.0, 0.0), AngleFormat=0, TextPrecision=0,
                              ExtLine1StartPoint=(0.0, 0.0, 0.0), ExtLine1EndPoint=(1.0, 0.0, 0.0),
                              ExtLine2StartPoint=(0.0, 0.0, 0.0), ExtLine2EndPoint=(1.0, 1.0, 0.0),
                              **angular).Handle

    # blocks: PUMP holds a nested NOZZLE, NOZZLE holds a nested BOLT, BOLT holds itself (a cycle the walk must survive)
    pump = doc.add_block("PUMP", origin=(0.0, 0.0, 0.0))
    pump.add("AcDbCircle", "GEOM", Center=(0.0, 0.0, 0.0), Radius=10.0, Normal=(0.0, 0.0, 1.0))
    pump.add("AcDbAttributeDefinition", "TEXT", TagString="TAG", PromptString="Tag?", TextString="P-101",
             InsertionPoint=(0.0, -12.0, 0.0), Height=2.5, Rotation=0.0, Constant=False)
    pump.add("AcDbBlockReference", "0", Name="NOZZLE", EffectiveName="NOZZLE", InsertionPoint=(10.0, 0.0, 0.0),
             XScaleFactor=1.0, YScaleFactor=1.0, ZScaleFactor=1.0, Rotation=0.0, Normal=(0.0, 0.0, 1.0),
             HasAttributes=False)
    nozzle = doc.add_block("NOZZLE")
    nozzle.add("AcDbLine", "GEOM", StartPoint=(0.0, 0.0, 0.0), EndPoint=(5.0, 0.0, 0.0))
    nozzle.add("AcDbBlockReference", "0", Name="BOLT", EffectiveName="BOLT", InsertionPoint=(0.0, 0.0, 0.0),
               XScaleFactor=1.0, YScaleFactor=1.0, ZScaleFactor=1.0, Rotation=0.0, Normal=(0.0, 0.0, 1.0),
               HasAttributes=False)
    bolt = doc.add_block("BOLT")
    bolt.add("AcDbCircle", "GEOM", Center=(0.0, 0.0, 0.0), Radius=1.0, Normal=(0.0, 0.0, 1.0))
    bolt.add("AcDbBlockReference", "0", Name="BOLT", EffectiveName="BOLT", InsertionPoint=(0.0, 0.0, 0.0),
             XScaleFactor=1.0, YScaleFactor=1.0, ZScaleFactor=1.0, Rotation=0.0, Normal=(0.0, 0.0, 1.0),
             HasAttributes=False)
    doc.add_block("SITE-XREF", is_xref=True, path="..\\site.dwg")

    tag = type("Attr", (), {"ObjectName": "AcDbAttribute", "TagString": "TAG", "TextString": "P-101A"})()
    h["insert"] = ms.add("AcDbBlockReference", "0", Name="PUMP", EffectiveName="PUMP",
                         InsertionPoint=(200.0, 0.0, 0.0), XScaleFactor=2.0, YScaleFactor=2.0, ZScaleFactor=1.0,
                         Rotation=math.pi / 2, Normal=(0.0, 0.0, 1.0), HasAttributes=True,
                         GetAttributes=lambda: (tag,)).Handle
    h["xref"] = ms.add("AcDbBlockReference", "0", Name="SITE-XREF", EffectiveName="SITE-XREF",
                       InsertionPoint=(0.0, 0.0, 0.0), XScaleFactor=1.0, YScaleFactor=1.0, ZScaleFactor=1.0,
                       Rotation=0.0, Normal=(0.0, 0.0, 1.0), HasAttributes=False).Handle
    h["pipe"] = ms.add("AeccDbPipe", "C-ROAD").Handle
    h["hatch"] = ms.add("AcDbHatch", "GEOM", PatternName="ANSI31").Handle
    h["broken"] = ms.add("AcDbCircle", "GEOM", Normal=(0.0, 0.0, 1.0), Radius=3.0).Handle  # no Center

    sheet = doc.add_layout("Vista A", 1)
    h["viewport"] = sheet.add("AcDbViewport", "0", Center=(148.5, 105.0, 0.0), Width=250.0, Height=180.0,
                              Target=(0.0, 0.0, 0.0), Direction=(0.0, 0.0, 1.0), CustomScale=0.02,
                              StandardScale=0, TwistAngle=0.0).Handle
    h["sheet_text"] = sheet.add("AcDbText", "TEXT", TextString="VISTA A", InsertionPoint=(10.0, 10.0, 0.0),
                                Height=5.0, Rotation=0.0, StyleName="Standard").Handle
    h["sheet_dim"] = sheet.add("AcDbRotatedDimension", "DIM", Measurement=30.0, TextOverride="",
                               TextPosition=(0.0, 0.0, 0.0), Rotation=0.0, **DIM_FORMAT).Handle
    doc.add_layout("Vista Z", 2)
    return FakeApp(doc), doc, h


def total_entities(doc):
    return sum(block.Count for block in doc.Blocks.items if not block.IsXRef)
