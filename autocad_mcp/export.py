"""Cemengal: export_drawing, a complete read-only export of an open drawing, run in the background
(docs/decisions/0006; the file's shape: docs/concepts/export-schema.md).

- ComReader reads COM properties with a DISPID cache: one GetIDsOfNames per (object type, name), then Invoke on
  the raw IDispatch; pywin32's late binding instead asks AutoCAD for the type info of every object it wraps.
- read_drawing walks the layouts (model space and every paper space), then the referenced block definitions,
  and counts every entity by type as read, skipped (with the reason) or failed. It never writes to the drawing.
- ExportJobs runs read_drawing on its own thread and COM apartment, with a proxy marshalled from the server's
  connection, and writes one JSON under %TEMP%\\Cemengal\\AutocadMCP\\exports\\ (docs/decisions/0003). Limits end a
  job as failed with the reason; a failed or cancelled job keeps <name>.failed.json, never a plain .json.
"""
import collections
import hashlib
import itertools
import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pythoncom

from autocad_mcp.export_text import ALT_TO_LINEAR, displayed_text, mtext_plain, text_plain
from autocad_mcp.temp_files import TempFolder

SCHEMA, SCHEMA_VERSION = "cemengal.autocad.export", 1
# a drawing's stem in an export's name: %TEMP%\Cemengal\AutocadMCP\exports\ (~60) + 80 + "-yyyyMMdd-HHmmss-NN.failed.json"
# (31) stays under Windows' 260-character path (QA-8)
MAX_STEM = 80
DISP_E_UNKNOWNNAME = -2147352570
DISP_E_MEMBERNOTFOUND = -2147352573
RPC_E_CALL_REJECTED = -2147418111
RPC_E_SERVERCALL_RETRYLATER = -2147417846
PyIDispatch = pythoncom.TypeIIDs[pythoncom.IID_IDispatch]
TEMPORARY = ("Exports are temporary: %TEMP%\\Cemengal\\AutocadMCP\\exports\\ keeps the last 3 exports, for 7 days "
             "at most; the newest export, and the newest complete one, are never pruned. Copy what you need.")


@dataclass
class Limits:
    """Caps that end a job as failed, with the reason; they never shorten the file silently."""
    max_entities: int = int(os.environ.get("ACAD_EXPORT_MAX_ENTITIES", "200000"))
    max_seconds: float = float(os.environ.get("ACAD_EXPORT_MAX_SECONDS", "3600"))
    max_bytes: int = int(os.environ.get("ACAD_EXPORT_MAX_BYTES", str(100 * 1024 * 1024)))
    block_depth: int = int(os.environ.get("ACAD_EXPORT_BLOCK_DEPTH", "4"))
    busy_patience: float = float(os.environ.get("ACAD_EXPORT_BUSY_PATIENCE", "300"))

    @classmethod
    def given(cls, **values):
        """The defaults, with each value that is not None."""
        return cls(**{k: v for k, v in values.items() if v is not None})


class Unavailable(Exception):
    """The object's COM interface has no such member."""


class JobStop(Exception):
    """Ends a job; the message is the reason."""


class Busy(JobStop):
    pass


class LimitReached(JobStop):
    pass


class Cancelled(JobStop):
    pass


def _code(error):
    return error.args[0] if getattr(error, "args", None) else None


def com_busy(error):
    return isinstance(error, pythoncom.com_error) and _code(error) in (RPC_E_CALL_REJECTED,
                                                                        RPC_E_SERVERCALL_RETRYLATER)


def one_line(text):
    return " | ".join(part.strip() for part in str(text).splitlines() if part.strip())


class ComReader:
    """Reads COM properties and calls COM methods, waiting while AutoCAD is busy (up to `patience` seconds).

    A raw IDispatch (or a pywin32 CDispatch, through its _oleobj_) goes through the DISPID cache and comes back
    raw; anything else (the tests' fakes) is read with getattr. A member the interface lacks raises Unavailable.
    """

    def __init__(self, is_busy=com_busy, patience=300.0, wait=0.25, checkpoint=None, on_wait=None,
                 raw_types=(PyIDispatch,)):
        self.is_busy, self.patience, self.wait = is_busy, patience, wait
        self.checkpoint = checkpoint or (lambda: None)
        self.on_wait = on_wait or (lambda: None)
        self.raw_types = raw_types
        self.ids = {}
        self.calls = self.busy_waits = 0
        self.waiting = False

    def get(self, obj, name, kind=""):
        return self._invoke(obj, name, kind, pythoncom.DISPATCH_PROPERTYGET, ())

    def call(self, obj, name, *args, kind=""):
        return self._invoke(obj, name, kind, pythoncom.DISPATCH_METHOD, args)

    def _raw(self, obj):
        if isinstance(obj, self.raw_types):
            return obj
        attrs = getattr(obj, "__dict__", None)
        ole = attrs.get("_oleobj_") if isinstance(attrs, dict) else None
        return ole if isinstance(ole, self.raw_types) else None

    def _invoke(self, obj, name, kind, flags, args):
        self.calls += 1
        ole = self._raw(obj)
        if ole is None:
            try:
                value = self._ready(lambda: getattr(obj, name))
            except AttributeError:
                raise Unavailable(name) from None
            return self._ready(lambda: value(*args)) if flags == pythoncom.DISPATCH_METHOD else value
        key = (kind, name)
        if key not in self.ids:
            try:
                self.ids[key] = self._ready(lambda: ole.GetIDsOfNames(0, name))
            except pythoncom.com_error as e:
                if _code(e) != DISP_E_UNKNOWNNAME:
                    raise
                self.ids[key] = None
        dispid = self.ids[key]
        if dispid is None:
            raise Unavailable(name)
        if flags == pythoncom.DISPATCH_PROPERTYGET:
            flags |= pythoncom.DISPATCH_METHOD  # as pywin32's late binding asks for a property
        try:
            return self._ready(lambda: ole.Invoke(dispid, 0, flags, True, *args))
        except pythoncom.com_error as e:
            if _code(e) == DISP_E_MEMBERNOTFOUND:
                raise Unavailable(name) from None
            raise

    def _ready(self, func):
        started = None
        try:
            while True:
                try:
                    return func()
                except Exception as e:
                    if not self.is_busy(e):
                        raise
                    now = time.monotonic()
                    if started is None:
                        started, self.waiting = now, True
                    if now - started >= self.patience:
                        raise Busy(f"AutoCAD stayed busy for {self.patience:g} s (is a command or dialog open?)")
                    self.busy_waits += 1
                    self.on_wait()
                    self.checkpoint()
                    time.sleep(self.wait)
        finally:
            if started is not None:
                self.waiting = False


# --- values ---------------------------------------------------------------------------------------------------

def _clean(value):
    if isinstance(value, (tuple, list)):
        return [_clean(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def point(value):
    return [float(v) for v in value]


def points(stride):
    def convert(flat):
        flat = [float(v) for v in flat]
        return [flat[i:i + stride] for i in range(0, len(flat) - stride + 1, stride)]
    return convert


INSUNITS = ["Unitless", "Inches", "Feet", "Miles", "Millimeters", "Centimeters", "Meters", "Kilometers",
            "Microinches", "Mils", "Yards", "Angstroms", "Nanometers", "Microns", "Decimeters", "Decameters",
            "Hectometers", "Gigameters", "Astronomical units", "Light years", "Parsecs", "US Survey Feet",
            "US Survey Inch", "US Survey Yard", "US Survey Mile"]

# --- what each entity type gives ------------------------------------------------------------------------------

SIMPLE = {
    "AcDbLine": ("line", [("StartPoint", "start", point), ("EndPoint", "end", point)]),
    "AcDbArc": ("arc", [("Center", "center", point), ("Radius", "radius", float), ("StartAngle", "start_angle", float),
                        ("EndAngle", "end_angle", float), ("Normal", "normal", point)]),
    "AcDbCircle": ("circle", [("Center", "center", point), ("Radius", "radius", float), ("Normal", "normal", point)]),
    "AcDbEllipse": ("ellipse", [("Center", "center", point), ("MajorAxis", "major_axis", point),
                                ("RadiusRatio", "radius_ratio", float), ("StartAngle", "start_angle", float),
                                ("EndAngle", "end_angle", float), ("Normal", "normal", point)]),
    "AcDbPoint": ("point", [("Coordinates", "position", point)]),
    "AcDbXline": ("xline", [("BasePoint", "base_point", point), ("DirectionVector", "direction", point)]),
    "AcDbRay": ("ray", [("BasePoint", "base_point", point), ("DirectionVector", "direction", point)]),
    "AcDbAttributeDefinition": ("attribute_definition", [
        ("TagString", "tag", str), ("PromptString", "prompt", str), ("TextString", "default", str),
        ("InsertionPoint", "position", point), ("Height", "height", float), ("Rotation", "rotation", float),
        ("Constant", "constant", bool)]),
    "AcDbViewport": ("viewport", [
        ("Center", "center", point), ("Width", "width", float), ("Height", "height", float),
        ("Target", "target", point), ("Direction", "direction", point), ("CustomScale", "custom_scale", float),
        ("StandardScale", "standard_scale", int), ("TwistAngle", "twist_angle", float)]),
}
# not in ActiveX's interfaces: reported as unavailable, never invented (an in-process reader would have them)
NEVER = {
    "AcDbViewport": ["view_center", "frozen_layers"],
}

DIM_TYPES = {"AcDbRotatedDimension": "rotated", "AcDbAlignedDimension": "aligned",
             "AcDb2LineAngularDimension": "angular", "AcDb3PointAngularDimension": "angular",
             "AcDbRadialDimension": "radial", "AcDbDiametricDimension": "diametric",
             "AcDbOrdinateDimension": "ordinate", "AcDbArcDimension": "arc_length",
             "AcDbRadialDimensionLarge": "radial_large"}
DIM_POINTS = {
    "AcDbAlignedDimension": [("ExtLine1Point", "ext_line1_point"), ("ExtLine2Point", "ext_line2_point")],
    "AcDb2LineAngularDimension": [("ExtLine1StartPoint", "ext_line1_start_point"),
                                  ("ExtLine1EndPoint", "ext_line1_end_point"),
                                  ("ExtLine2StartPoint", "ext_line2_start_point"),
                                  ("ExtLine2EndPoint", "ext_line2_end_point")],
    "AcDb3PointAngularDimension": [("AngleVertex", "angle_vertex"), ("ExtLine1EndPoint", "ext_line1_end_point"),
                                   ("ExtLine2EndPoint", "ext_line2_end_point")],
    "AcDbArcDimension": [("ArcPoint", "arc_point"), ("CenterPoint", "center_point"),
                         ("ExtLine1Point", "ext_line1_point"), ("ExtLine2Point", "ext_line2_point"),
                         ("Leader1Point", "leader1_point"), ("Leader2Point", "leader2_point")],
    "AcDbRadialDimensionLarge": [("Center", "center_point"), ("ChordPoint", "chord_point"),
                                 ("OverrideCenter", "override_center"), ("JogLocation", "jog_location")],
}
DIM_NEVER = {  # checked in AutoCAD 2025's type info, 2026-11-01
    "AcDbRotatedDimension": ["ext_line1_point", "ext_line2_point"],
    "AcDbRadialDimension": ["center_point", "chord_point"],
    "AcDbDiametricDimension": ["chord_point", "far_chord_point"],
    "AcDbOrdinateDimension": ["feature_point", "leader_end_point"],
}
LINEAR_FORMAT = [("UnitsFormat", "units_format", int), ("PrimaryUnitsPrecision", "precision", int),
                 ("LinearScaleFactor", "linear_scale_factor", float), ("RoundDistance", "round_distance", float),
                 ("SuppressZeroFeet", "suppress_zero_feet", bool), ("SuppressZeroInches", "suppress_zero_inches", bool)]
ANGULAR_FORMAT = [("AngleFormat", "angle_format", int), ("TextPrecision", "precision", int)]
COMMON_FORMAT = [("SuppressLeadingZeros", "suppress_leading_zeros", bool),
                 ("SuppressTrailingZeros", "suppress_trailing_zeros", bool),
                 ("DecimalSeparator", "decimal_separator", str), ("TextPrefix", "prefix", str),
                 ("TextSuffix", "suffix", str), ("ToleranceDisplay", "tolerance_display", int)]
TOLERANCE = [("ToleranceUpperLimit", "tolerance_upper", float), ("ToleranceLowerLimit", "tolerance_lower", float),
             ("TolerancePrecision", "tolerance_precision", int)]
ALT_FORMAT = [("AltUnitsFormat", "units_format_com", int), ("AltUnitsPrecision", "precision", int),
              ("AltUnitsScale", "scale", float), ("AltRoundDistance", "round_distance", float),
              ("AltSuppressLeadingZeros", "suppress_leading_zeros", bool),
              ("AltSuppressTrailingZeros", "suppress_trailing_zeros", bool),
              ("AltSuppressZeroFeet", "suppress_zero_feet", bool), ("AltSuppressZeroInches", "suppress_zero_inches", bool),
              ("AltTextPrefix", "prefix", str),
              ("AltTextSuffix", "suffix", str)]

SKIPPED = {
    "AcDbHatch": "hatch: boundary loops and pattern are not exported in v1",
    "AcDbSolid": "2D solid: not exported in v1",
    "AcDbTrace": "trace: not exported in v1",
    "AcDbFace": "3D face: not exported in v1",
    "AcDb3dSolid": "3D solid: its ACIS geometry is not readable over COM",
    "AcDbRegion": "region: its ACIS geometry is not readable over COM",
    "AcDbBody": "body: its ACIS geometry is not readable over COM",
    "AcDbPolyFaceMesh": "polyface mesh: not exported in v1",
    "AcDbPolygonMesh": "polygon mesh: not exported in v1",
    "AcDbRasterImage": "raster image: not exported in v1",
    "AcDbWipeout": "wipeout: not exported in v1",
    "AcDbOle2Frame": "OLE object: not exported in v1",
    "AcDbMline": "multiline: not exported in v1",
    "AcDbFcf": "geometric tolerance frame: not exported in v1",
    "AcDbProxyEntity": "proxy entity: no geometry over COM",
}


def skip_reason(object_name):
    if object_name in SKIPPED:
        return SKIPPED[object_name]
    if object_name.startswith("Aecc"):
        return "Civil 3D object: not exported (plain AutoCAD geometry only)"
    if object_name.startswith("Aec"):
        return "AutoCAD Architecture object: not exported (plain AutoCAD geometry only)"
    return f"{object_name}: not exported in v1 (no reader for this type)"


# --- progress -------------------------------------------------------------------------------------------------

class Progress:
    """What the walk has done, read by get_export_status from another thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.spaces, self.blocks, self.entities_read = [], {"read": 0, "total": 0}, 0

    def set_spaces(self, spaces):
        with self.lock:
            self.spaces = [{"layout": name, "read": 0, "total": total} for name, total in spaces]

    def advance(self, layout=None):
        with self.lock:
            self.entities_read += 1
            for space in self.spaces:
                if layout is not None and space["layout"] == layout:
                    space["read"] += 1
                    break

    def block_queued(self):
        with self.lock:
            self.blocks["total"] += 1

    def block_done(self):
        with self.lock:
            self.blocks["read"] += 1

    def snapshot(self):
        with self.lock:
            return {"spaces": [dict(s) for s in self.spaces], "blocks": dict(self.blocks),
                    "entities_read": self.entities_read}


# --- the walk -------------------------------------------------------------------------------------------------

class DrawingReader:
    def __init__(self, app, doc, limits, reader=None, progress=None, cancelled=None, clock=time.monotonic):
        self.app, self.doc, self.limits = app, doc, limits
        self.r = reader or ComReader(patience=limits.busy_patience)
        self.r.checkpoint = self.check
        self.progress = progress or Progress()
        self.cancelled = cancelled or (lambda: False)
        self.clock = clock
        self.started = clock()
        self.counts, self.reasons = {}, {}
        self.seen = self.size = 0
        self.queue, self.queued, self.not_read = collections.deque(), set(), []
        self.warnings = []

    # limits and cancellation, checked before each entity and while waiting on a busy AutoCAD
    def check(self):
        if self.cancelled():
            raise Cancelled(f"cancelled by cancel_export after {self.seen} entities")
        if self.clock() - self.started > self.limits.max_seconds:
            raise LimitReached(f"max_seconds {self.limits.max_seconds:g} reached after {self.seen} entities")

    def _get(self, obj, name, kind):
        return self.r.get(obj, name, kind=kind)

    def _field(self, obj, rec, kind, prop, name, convert=_clean, into=None, label=None):
        """One property into `into` (default rec); unavailable or failing, it is None and rec says why."""
        target = rec if into is None else into
        label = label or name
        try:
            value = self.r.get(obj, prop, kind=kind)
            value = None if value is None else convert(value)
        except JobStop:
            raise
        except Unavailable:
            rec.setdefault("unavailable", []).append(label)
            value = None
        except Exception as e:
            rec.setdefault("errors", {})[label] = one_line(e)
            value = None
        target[name] = value
        return value

    def _call(self, obj, rec, kind, method, label, *args):
        try:
            return self.r.call(obj, method, *args, kind=kind)
        except JobStop:
            raise
        except Unavailable:
            rec.setdefault("unavailable", []).append(label)
        except Exception as e:
            rec.setdefault("errors", {})[label] = one_line(e)
        return None

    def _count(self, object_name, outcome, reason=None):
        c = self.counts.setdefault(object_name, {"read": 0, "skipped": 0, "failed": 0, "with_errors": 0})
        c[outcome] += 1
        if reason and outcome == "skipped":
            self.reasons.setdefault(object_name, reason)

    def _account(self, rec):
        self.size += len(json.dumps(rec, ensure_ascii=False, separators=(",", ":"))) + 1
        if self.size > self.limits.max_bytes:
            raise LimitReached(f"max_bytes {self.limits.max_bytes} reached after {self.seen} entities "
                               f"(about {self.size} bytes)")

    # the header
    def header(self):
        app = {}
        self._field(self.app, app, "Application", "Name", "name", str)
        self._field(self.app, app, "Application", "Version", "version", str)
        drawing = {}
        self._field(self.doc, drawing, "Document", "Name", "name", str)
        self._field(self.doc, drawing, "Document", "FullName", "full_path", str)
        for var, name in (("ACADVER", "version"), ("INSUNITS", "insunits"), ("MEASUREMENT", "measurement")):
            drawing[name] = _clean(self._call(self.doc, drawing, "Document", "GetVariable", name, var))
        units = drawing.get("insunits")
        drawing["insunits_name"] = INSUNITS[units] if isinstance(units, int) and 0 <= units < len(INSUNITS) else None
        drawing["measurement_name"] = {0: "imperial", 1: "metric"}.get(drawing.get("measurement"))
        drawing.setdefault("unavailable", []).append("dwg_format")  # COM gives the session's release, not the file's
        return app, drawing

    def layouts(self):
        layouts = self._get(self.doc, "Layouts", "Document")
        found = []
        for i in range(int(self._get(layouts, "Count", "Layouts"))):
            layout = self.r.call(layouts, "Item", i, kind="Layouts")
            block = self._get(layout, "Block", "AcDbLayout")
            name = str(self._get(block, "Name", "Block"))
            entry = {"name": str(self._get(layout, "Name", "AcDbLayout")),
                     "is_model": bool(self._get(layout, "ModelType", "AcDbLayout")),
                     "tab_order": int(self._get(layout, "TabOrder", "AcDbLayout")),
                     "block": name, "entity_count": int(self._get(block, "Count", "Block:" + name)),
                     "viewports": []}
            found.append((entry, block))
        found.sort(key=lambda f: (not f[0]["is_model"], f[0]["tab_order"]))
        return found

    # one entity
    def _entity_at(self, block, block_name, index, ctx, depth):
        self.check()
        if self.seen >= self.limits.max_entities:
            raise LimitReached(f"max_entities {self.limits.max_entities} reached; the drawing has more")
        self.seen += 1
        try:
            entity = self.r.call(block, "Item", index, kind="Block:" + block_name)
            object_name = str(self.r.get(entity, "ObjectName", kind="AcDbObject"))
        except JobStop:
            raise
        except Exception as e:
            rec = {"type": "unreadable", "object_name": None, "handle": None, "layer": None, **ctx,
                   "index": index, "failed": one_line(e)}
            self._count("(unreadable)", "failed")
            self._account(rec)
            return rec
        rec = {"type": None, "object_name": object_name, "handle": None, "layer": None, **ctx}
        self._field(entity, rec, object_name, "Handle", "handle", str)
        self._field(entity, rec, object_name, "Layer", "layer", str)
        reader = self._reader_for(object_name)
        if reader is None:
            rec["type"] = "other"
            rec["skipped"] = skip_reason(object_name)
            self._count(object_name, "skipped", rec["skipped"])
        else:
            reader(entity, rec, object_name, depth)
            for name in NEVER.get(object_name, []):
                rec[name] = None
                rec.setdefault("unavailable", []).append(name)
            self._count(object_name, "read")
            if rec.get("errors"):
                self._count(object_name, "with_errors")
        self._account(rec)
        return rec

    def _reader_for(self, object_name):
        if object_name in SIMPLE:
            return self._simple
        if object_name in DIM_TYPES:
            return self._dimension
        return {"AcDbPolyline": self._lwpolyline, "AcDb2dPolyline": self._polyline2d,
                "AcDb3dPolyline": self._polyline3d, "AcDbSpline": self._spline, "AcDbText": self._text,
                "AcDbMText": self._mtext, "AcDbLeader": self._leader, "AcDbMLeader": self._mleader,
                "AcDbBlockReference": self._insert, "AcDbMInsertBlock": self._insert,
                "AcDbTable": self._table}.get(object_name)

    def _simple(self, e, rec, k, depth):
        rec["type"], props = SIMPLE[k]
        for prop, name, convert in props:
            self._field(e, rec, k, prop, name, convert)

    def _bulges(self, e, rec, k, count):
        bulges = []
        for i in range(count):
            if i and i % 100 == 0:
                self.check()
            value = self._call(e, rec, k, "GetBulge", "bulges", i)
            if value is None:
                rec["bulges"] = None
                return
            bulges.append(float(value))
        rec["bulges"] = bulges

    def _lwpolyline(self, e, rec, k, depth):
        rec["type"] = "polyline"
        vertices = self._field(e, rec, k, "Coordinates", "vertices", points(2))
        self._field(e, rec, k, "Closed", "closed", bool)
        self._field(e, rec, k, "Elevation", "elevation", float)
        self._bulges(e, rec, k, len(vertices or []))

    def _polyline2d(self, e, rec, k, depth):
        rec["type"] = "polyline2d"
        vertices = self._field(e, rec, k, "Coordinates", "vertices", points(3))
        self._field(e, rec, k, "Closed", "closed", bool)
        self._field(e, rec, k, "Type", "fit_type", int)
        self._bulges(e, rec, k, len(vertices or []))

    def _polyline3d(self, e, rec, k, depth):
        rec["type"] = "polyline3d"
        self._field(e, rec, k, "Coordinates", "vertices", points(3))
        self._field(e, rec, k, "Closed", "closed", bool)

    def _spline(self, e, rec, k, depth):
        # exact: control points, knots, weights and fit points; the agent evaluates the curve if it needs to
        rec["type"] = "spline"
        self._field(e, rec, k, "Degree", "degree", int)
        self._field(e, rec, k, "Closed", "closed", bool)
        rational = self._field(e, rec, k, "IsRational", "rational", bool)
        self._field(e, rec, k, "ControlPoints", "control_points", points(3))
        self._field(e, rec, k, "Knots", "knots", lambda v: [float(x) for x in v])
        if rational:
            self._field(e, rec, k, "Weights", "weights", lambda v: [float(x) for x in v])
        else:
            rec["weights"] = None
        fits = self._field(e, rec, k, "NumberOfFitPoints", "fit_point_count", int)
        if fits:
            self._field(e, rec, k, "FitPoints", "fit_points", points(3))
        else:
            rec["fit_points"] = []

    def _text_common(self, e, rec, k):
        self._field(e, rec, k, "InsertionPoint", "position", point)
        self._field(e, rec, k, "Height", "height", float)
        self._field(e, rec, k, "Rotation", "rotation", float)
        self._field(e, rec, k, "StyleName", "style", str)

    def _text(self, e, rec, k, depth):
        rec["type"] = "text"
        raw = self._field(e, rec, k, "TextString", "raw", str)
        rec["plain"] = text_plain(raw)
        self._text_common(e, rec, k)
        self._field(e, rec, k, "Alignment", "alignment", int)
        self._field(e, rec, k, "TextAlignmentPoint", "alignment_point", point)

    def _mtext(self, e, rec, k, depth):
        rec["type"] = "mtext"
        raw = self._field(e, rec, k, "TextString", "raw", str)
        rec["plain"] = mtext_plain(raw)
        self._text_common(e, rec, k)
        self._field(e, rec, k, "Width", "width", float)
        self._field(e, rec, k, "AttachmentPoint", "attachment", int)

    def _leader(self, e, rec, k, depth):
        rec["type"] = "leader"
        self._field(e, rec, k, "Coordinates", "points", points(3))
        self._field(e, rec, k, "Type", "leader_type", int)
        rec["annotation_handle"] = rec["raw"] = rec["plain"] = None
        note = self._field(e, rec, k, "Annotation", "annotation", lambda v: v, into={})
        if note is None:
            return
        kind = str(self.r.get(note, "ObjectName", kind="AcDbObject"))
        self._field(note, rec, kind, "Handle", "annotation_handle", str)
        if kind == "AcDbMText":
            rec["plain"] = mtext_plain(self._field(note, rec, kind, "TextString", "raw", str))

    def _mleader(self, e, rec, k, depth):
        rec["type"] = "multileader"
        content = self._field(e, rec, k, "ContentType", "content_type", int)
        rec["raw"] = rec["plain"] = None
        if content == 2:  # acMTextContent
            rec["plain"] = mtext_plain(self._field(e, rec, k, "TextString", "raw", str))
        elif content == 1:  # acBlockContent
            self._field(e, rec, k, "ContentBlockName", "content_block", str)
        lines = []
        for i in range(self._field(e, rec, k, "LeaderCount", "leader_count", int, into={}) or 0):
            for j in self._call(e, rec, k, "GetLeaderLineIndexes", "leader_lines", i) or ():
                vertices = self._call(e, rec, k, "GetLeaderLineVertices", "leader_lines", j)
                if vertices is not None:
                    lines.append(points(3)(vertices))
        rec["leader_lines"] = lines

    def _dimension(self, e, rec, k, depth):
        rec["type"], dim_type = "dimension", DIM_TYPES[k]
        rec["dim_type"] = dim_type
        measurement = self._field(e, rec, k, "Measurement", "measurement", float)
        override = self._field(e, rec, k, "TextOverride", "text_override", str)
        self._field(e, rec, k, "TextPosition", "text_position", point)
        self._field(e, rec, k, "TextRotation", "text_rotation", float)
        if dim_type == "rotated":
            self._field(e, rec, k, "Rotation", "rotation", float)
        found = {}
        for prop, name in DIM_POINTS.get(k, []):
            if self._field(e, rec, k, prop, name, point, into=found) is None:
                found.pop(name)
        rec["points"] = found
        rec.setdefault("unavailable", []).extend(DIM_NEVER.get(k, []) + ["dimension_line_points"])
        style = {}
        self._field(e, rec, k, "StyleName", "name", str, into=style, label="style.name")
        angular = dim_type == "angular"
        for prop, name, convert in (ANGULAR_FORMAT if angular else LINEAR_FORMAT) + COMMON_FORMAT:
            self._field(e, rec, k, prop, name, convert, into=style, label="style." + name)
        if style.get("tolerance_display"):
            for prop, name, convert in TOLERANCE:
                self._field(e, rec, k, prop, name, convert, into=style, label="style." + name)
        if dim_type == "arc_length":
            self._field(e, rec, k, "SymbolPosition", "symbol_position", int, into=style, label="style.symbol_position")
        style["alt_units"] = None
        if not angular and self._field(e, rec, k, "AltUnits", "alt_units", bool, into={}, label="style.alt_units"):
            alt = {}
            for prop, name, convert in ALT_FORMAT:
                self._field(e, rec, k, prop, name, convert, into=alt, label="style.alt_units." + name)
            alt["units_format"] = ALT_TO_LINEAR.get(alt.get("units_format_com"), alt.get("units_format_com"))
            style["alt_units"] = alt
        rec["style"] = style
        shown = displayed_text(dim_type, measurement, override, style)
        rec["displayed_text"], rec["displayed_text_plain"] = shown["text"], shown["plain"]
        rec["displayed_text_source"], rec["displayed_text_approximate"] = shown["source"], shown["approximate"]
        rec["formatted_measurement"] = shown["formatted_measurement"]

    def _insert(self, e, rec, k, depth):
        rec["type"] = "insert"
        name = self._field(e, rec, k, "Name", "name", str)
        self._field(e, rec, k, "EffectiveName", "effective_name", str)
        self._field(e, rec, k, "InsertionPoint", "position", point)
        scale = {}
        for prop, axis in (("XScaleFactor", "x"), ("YScaleFactor", "y"), ("ZScaleFactor", "z")):
            self._field(e, rec, k, prop, axis, float, into=scale, label="scale." + axis)
        rec["scale"] = [scale["x"], scale["y"], scale["z"]]
        self._field(e, rec, k, "Rotation", "rotation", float)
        self._field(e, rec, k, "Normal", "normal", point)
        if k == "AcDbMInsertBlock":
            for prop, field_name, convert in (("Rows", "rows", int), ("Columns", "columns", int),
                                              ("RowSpacing", "row_spacing", float),
                                              ("ColumnSpacing", "column_spacing", float)):
                self._field(e, rec, k, prop, field_name, convert)
        attributes = []
        if self._field(e, rec, k, "HasAttributes", "has_attributes", bool, into={}):
            for a in self._call(e, rec, k, "GetAttributes", "attributes") or ():
                attr = {}
                self._field(a, rec, "AcDbAttribute", "TagString", "tag", str, into=attr, label="attributes.tag")
                self._field(a, rec, "AcDbAttribute", "TextString", "value", str, into=attr, label="attributes.value")
                attributes.append(attr)
        rec["attributes"] = attributes
        if name:
            self._want_block(name, depth + 1)

    def _table(self, e, rec, k, depth):
        rec["type"] = "table"
        rows = self._field(e, rec, k, "Rows", "rows", int) or 0
        columns = self._field(e, rec, k, "Columns", "columns", int) or 0
        cells = []
        for r in range(rows):
            self.check()
            cells.append([_clean(self._call(e, rec, k, "GetText", "cells", r, c)) for c in range(columns)])
        rec["cells"] = cells

    # block definitions
    def _want_block(self, name, depth):
        if name in self.queued:
            return
        if depth > self.limits.block_depth:
            if not any(n["block"] == name for n in self.not_read):
                self.not_read.append({"block": name, "depth": depth,
                                      "reason": f"block_depth limit {self.limits.block_depth}"})
            return
        self.queued.add(name)
        self.queue.append((name, depth))
        self.progress.block_queued()

    def blocks(self):
        out = {}
        if not self.queue:
            return out
        collection = self._get(self.doc, "Blocks", "Document")
        while self.queue:
            name, depth = self.queue.popleft()
            self.check()
            entry = {"name": name, "depth": depth}
            out[name] = entry
            try:
                block = self.r.call(collection, "Item", name, kind="Blocks")
            except JobStop:
                raise
            except Exception as e:
                entry.update(entities=[], failed=one_line(e))
                self.progress.block_done()
                continue
            kind = "Block:" + name
            self._field(block, entry, kind, "Origin", "origin", point)
            if self._field(block, entry, kind, "IsXRef", "is_xref", bool):
                self._field(block, entry, kind, "Path", "path", str)
                entry.update(entities=[], skipped="external reference: its drawing is not walked")
                self.progress.block_done()
                continue
            count = self._field(block, entry, kind, "Count", "entity_count", int) or 0
            entry["entities"] = []
            for i in range(count):
                entry["entities"].append(self._entity_at(block, name, i, {"space": "block", "block": name}, depth))
                self.progress.advance()
            self.progress.block_done()
        return out

    def run(self):
        started_at = datetime.now().isoformat(timespec="seconds")
        application, drawing = self.header()
        layouts = self.layouts()
        drawing["spaces"] = [{"layout": l["name"], "is_model": l["is_model"], "block": l["block"]}
                             for l, _ in layouts]
        self.progress.set_spaces([(l["name"], l["entity_count"]) for l, _ in layouts])
        entities = []
        for layout, block in layouts:
            space = "model" if layout["is_model"] else "paper"
            for i in range(layout["entity_count"]):
                rec = self._entity_at(block, layout["block"], i, {"space": space, "layout": layout["name"]}, 0)
                if rec["type"] == "viewport":
                    layout["viewports"].append({k: v for k, v in rec.items()
                                                if k not in ("type", "object_name", "space", "layout")})
                entities.append(rec)
                self.progress.advance(layout["name"])
            try:
                now = int(self._get(block, "Count", "Block:" + layout["block"]))
                if now != layout["entity_count"]:
                    self.warnings.append(f"{layout['name']}: {layout['entity_count']} entities when the export "
                                         f"started, {now} at its end (the drawing changed meanwhile)")
            except JobStop:
                raise
            except Exception:
                pass
        blocks = self.blocks()
        elapsed = self.clock() - self.started
        total = {o: sum(c[o] for c in self.counts.values()) for o in ("read", "skipped", "failed")}
        return {
            "schema": SCHEMA, "schema_version": SCHEMA_VERSION, "complete": True,
            "export": {"started_at": started_at, "elapsed_s": round(elapsed, 3), "entities_read": self.seen,
                       "entities_per_second": round(self.seen / elapsed, 1) if elapsed > 0 else None,
                       "com_calls": self.r.calls, "busy_waits": self.r.busy_waits, "limits": asdict(self.limits),
                       "displayed_text_source": "computed from each dimension's format settings over COM"},
            "application": application, "drawing": drawing,
            "layouts": [l for l, _ in layouts], "entities": entities,
            "blocks": blocks, "blocks_not_read": self.not_read,
            "counts": {"by_type": self.counts, "skipped_reasons": self.reasons, "total": total},
            "warnings": self.warnings,
        }


def read_drawing(app, doc, limits=None, reader=None, progress=None, cancelled=None, clock=time.monotonic):
    """The whole export of one open drawing, as a dict (the file's content). Read only."""
    return DrawingReader(app, doc, limits or Limits(), reader, progress, cancelled, clock).run()


# --- the background job ---------------------------------------------------------------------------------------

class ExportJob:
    """running → done | failed | cancelled; the first final state stays."""

    def __init__(self, job_id, document, output_path, limits, clock=time.monotonic):
        self.job_id, self.document, self.output_path, self.limits = job_id, document, Path(output_path), limits
        self.clock = clock
        self.state, self.reason, self.result_path = "running", None, None
        self.cancel_requested = False
        self.started, self.ended = clock(), None
        self.progress, self.reader, self.thread = Progress(), None, None
        self.lock = threading.Lock()

    def request_cancel(self):
        self.cancel_requested = True

    def _end(self, state, path, reason=None):
        with self.lock:
            if self.state != "running":
                return False
            self.state, self.reason, self.result_path = state, reason, path
            self.ended = self.clock()
            return True

    def finish(self, path):
        return self._end("done", path)

    def fail(self, reason, path=None):
        return self._end("failed", path, one_line(reason))

    def mark_cancelled(self, path, reason="cancelled by cancel_export"):
        return self._end("cancelled", path, one_line(reason))

    def status(self):
        with self.lock:
            elapsed = (self.ended if self.ended is not None else self.clock()) - self.started
            progress = self.progress.snapshot()
            status = {"job_id": self.job_id, "state": self.state, "document": self.document,
                      "output_path": str(self.output_path),
                      "result_path": str(self.result_path) if self.result_path else None,
                      "elapsed_s": round(elapsed, 1), "progress": progress,
                      "entities_per_second": round(progress["entities_read"] / elapsed, 1) if elapsed > 0 else None,
                      "waiting_for_autocad": bool(self.reader and self.reader.waiting),
                      "cancel_requested": self.cancel_requested, "limits": asdict(self.limits)}
            if self.reason:
                status["reason"] = self.reason
            return status


def safe_stem(name):
    """The file-name stem for a drawing: no path, no reserved characters, at most MAX_STEM characters. A longer
    one keeps a readable prefix plus "~" and a hash of the whole stem, so two long names never share a stem and
    the path stays under Windows' 260 characters (QA-8)."""
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(str(name)).stem).strip(" .")
    if len(stem) > MAX_STEM:
        # not security: the hash only tells two long names apart in a file name; never-overwrite rests on the
        # -2/-3 suffixes and the exclusive create in reserve() (SEC-11)
        digest = hashlib.sha1(stem.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        stem = stem[:MAX_STEM - 9].rstrip(" .") + "~" + digest
    return stem or "drawing"


def reserve(folder, document, now):
    """(final, failed, partial) paths for a new export, the partial created so no other job takes the name.
    An existing export or failure of the same name is never overwritten: -2, -3, … are tried."""
    base = f"{safe_stem(document)}-{now:%Y%m%d-%H%M%S}"
    for n in itertools.count(1):
        name = base if n == 1 else f"{base}-{n}"
        final, failed, partial = folder / f"{name}.json", folder / f"{name}.failed.json", folder / f"{name}.json.partial"
        if final.exists() or failed.exists():
            continue
        try:
            with open(partial, "x", encoding="utf-8"):
                pass
        except FileExistsError:
            continue
        return final, failed, partial


class AppOpener:
    """Gives the export thread its own proxy to this AutoCAD: COM objects belong to the apartment that made them,
    so the server's proxy is marshalled, not shared (a fake, in the tests, is shared). The stream is used once,
    by the thread, or released (QA-4): calling it, or release(), consumes it."""

    def __init__(self, app):
        self.app = app
        ole = app if isinstance(app, PyIDispatch) else getattr(app, "__dict__", {}).get("_oleobj_")
        self.shared = not isinstance(ole, PyIDispatch)
        self.stream = None if self.shared else pythoncom.CoMarshalInterThreadInterfaceInStream(
            pythoncom.IID_IDispatch, ole)

    def __call__(self):
        if self.shared:
            return self.app
        if self.stream is None:
            raise RuntimeError("the marshalled AutoCAD proxy was already used or released")
        stream, self.stream = self.stream, None
        return pythoncom.CoGetInterfaceAndReleaseStream(stream, pythoncom.IID_IDispatch)

    def release(self):
        """Free the stream if no thread took it; harmless after use or twice."""
        if self.stream is not None:
            stream, self.stream = self.stream, None
            try:
                pythoncom.CoGetInterfaceAndReleaseStream(stream, pythoncom.IID_IDispatch)
            except pythoncom.com_error:
                pass


def app_opener(app):
    return AppOpener(app)


def find_document(reader, app, name, full_name):
    documents = reader.get(app, "Documents", kind="Application")
    by_name = None
    for i in range(int(reader.get(documents, "Count", kind="Documents"))):
        doc = reader.call(documents, "Item", i, kind="Documents")
        path = str(reader.get(doc, "FullName", kind="Document") or "")
        if full_name and path.lower() == full_name.lower():
            return doc
        if by_name is None and str(reader.get(doc, "Name", kind="Document")).lower() == name.lower():
            by_name = doc
    if by_name is None:
        raise JobStop(f"The drawing {name} is no longer open in AutoCAD")
    return by_name


class ExportJobs:
    """The server's export jobs: one runs at a time; finished ones stay for get_export_status."""

    def __init__(self, temp=None, is_busy=com_busy, clock=time.monotonic, now=datetime.now):
        self.temp, self.is_busy, self.clock, self.now = temp or TempFolder(), is_busy, clock, now
        self.jobs, self.lock = {}, threading.Lock()

    def start(self, app, document, full_name, limits):
        """Start a job on `app` (the server's Application). Its proxy is marshalled only once the job is
        accepted, and released if the thread cannot start (QA-4)."""
        with self.lock:
            running = [j for j in self.jobs.values() if j.state == "running"]
            if running:
                return {"error": "An export is already running: wait for it, or cancel it with cancel_export",
                        "job_id": running[0].job_id}
            try:
                final, failed, partial = reserve(self.temp.artefact_dir("exports"), document, self.now())
            except (ValueError, OSError) as e:  # ACC, a junctioned temp folder (known gap 17), a full disk
                return {"error": f"Cannot write the export: {one_line(e)}"}
            job = ExportJob(uuid.uuid4().hex[:12], document, final, limits, self.clock)
            self.jobs[job.job_id] = job
            opener = app_opener(app)
            job.thread = threading.Thread(target=self._run, args=(job, opener, full_name, failed, partial),
                                          name=f"export-{job.job_id}", daemon=True)
            try:
                job.thread.start()
            except Exception as e:
                opener.release()
                job.fail(f"Could not start the export thread: {e}")
                try:
                    partial.unlink()
                except OSError:
                    pass
                return {"error": f"Could not start the export: {one_line(e)}", "job_id": job.job_id}
            return {"success": True, "job_id": job.job_id, "state": job.state, "document": document,
                    "output_path": str(final), "note": TEMPORARY}

    def status(self, job_id):
        job = self.jobs.get(job_id)
        return job.status() if job else {"error": f"Unknown export job: {job_id}"}

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            return {"error": f"Unknown export job: {job_id}"}
        if job.state == "running":
            job.request_cancel()
        status = job.status()
        return {"success": True, "job_id": job_id, "state": status["state"],
                "cancel_requested": job.cancel_requested}

    def join(self, job_id, timeout=None):
        job = self.jobs.get(job_id)
        if job and job.thread:
            job.thread.join(timeout)

    def _run(self, job, open_app, full_name, failed, partial):
        pythoncom.CoInitialize()
        walk = None
        try:
            try:
                app = open_app()
                job.reader = ComReader(self.is_busy, patience=job.limits.busy_patience)
                doc = find_document(job.reader, app, job.document, full_name)
                walk = DrawingReader(app, doc, job.limits, job.reader, job.progress,
                                     lambda: job.cancel_requested, self.clock)
                text = json.dumps(walk.run(), ensure_ascii=False, separators=(",", ":"))
                size = len(text.encode("utf-8"))
                if size > job.limits.max_bytes:
                    raise LimitReached(f"max_bytes {job.limits.max_bytes} reached: the export is {size} bytes")
                partial.write_text(text, encoding="utf-8")
                os.rename(partial, job.output_path)  # never replaces an existing file
                job.finish(job.output_path)
            except Cancelled as e:
                job.mark_cancelled(self._keep_failed(job, walk, "cancelled", str(e), failed, partial), str(e))
            except Exception as e:
                reason = str(e) if isinstance(e, JobStop) else f"{type(e).__name__}: {e}"
                job.fail(reason, self._keep_failed(job, walk, "failed", reason, failed, partial))
        finally:
            try:
                if partial.exists():
                    partial.unlink()
            except OSError:
                pass
            getattr(open_app, "release", lambda: None)()  # a no-op once the thread took the stream (QA-4)
            self.temp.prune_exports()  # the last 3 hold in a long-running server too (known gap 16)
            pythoncom.CoUninitialize()

    def _keep_failed(self, job, walk, state, reason, failed, partial):
        """<name>.failed.json with the reason, for diagnosis; never a plain .json."""
        content = {"schema": SCHEMA, "schema_version": SCHEMA_VERSION, "complete": False, "state": state,
                   "reason": one_line(reason), "document": job.document,
                   "elapsed_s": round(self.clock() - job.started, 3), "progress": job.progress.snapshot(),
                   "limits": asdict(job.limits)}
        if walk is not None:
            content["counts"] = {"by_type": walk.counts, "skipped_reasons": walk.reasons}
        try:
            partial.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
            os.rename(partial, failed)
            return failed
        except OSError:
            return None
