"""An in-memory stand-in for AutoCAD's COM object model: just what AutoCADCOMServer touches."""
import itertools

import pythoncom


class FakeLayer:
    handles = itertools.count(0x100)

    def __init__(self, name, color=7):
        self.Name, self.Color, self.Freeze, self.Lock, self.Description = name, color, False, False, ""
        self.Handle, self.OwnerID = format(next(self.handles), "X"), 2  # owned by the layer table

    def Delete(self):
        raise AssertionError("a layer was deleted")


class FakeLayers:
    def __init__(self, names):
        self.items = [FakeLayer(n) for n in names]
        self.added = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, key):
        if isinstance(key, int):
            return self.items[key]
        for layer in self.items:
            if layer.Name.lower() == str(key).lower():
                return layer
        raise Exception(f"Key not found: {key}")

    def Add(self, name):
        layer = FakeLayer(name)
        self.items.append(layer)
        self.added.append(name)
        return layer


class FakeEntity:
    def __init__(self, space, object_name, layer, **props):
        self.space, self.ObjectName, self.Layer = space, object_name, layer
        self.Handle = format(next(space.handles), "X")
        self.Color, self.Visible, self.OwnerID, self.updates = 256, True, space.ObjectID, 0
        self.__dict__.update(props)

    def Delete(self):
        self.space.items.remove(self)

    def Update(self):
        self.updates += 1


class FakeModelSpace:
    ObjectID = 1

    def __init__(self, doc):
        self.doc, self.items, self.handles, self.item_calls = doc, [], itertools.count(0x7200), 0

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        self.item_calls += 1
        return self.items[i]

    def _add(self, object_name, **props):
        entity = FakeEntity(self, object_name, self.doc.ActiveLayer.Name, **props)
        self.items.append(entity)
        return entity

    def AddLine(self, start, end):
        return self._add("AcDbLine", StartPoint=tuple(start.value), EndPoint=tuple(end.value))

    def AddCircle(self, center, radius):
        return self._add("AcDbCircle", Center=tuple(center.value), Radius=radius)

    def AddArc(self, center, radius, start, end):
        return self._add("AcDbArc", Center=tuple(center.value), Radius=radius)

    def AddText(self, text, point, height):
        return self._add("AcDbText", TextString=text, InsertionPoint=tuple(point.value), Height=height)


class FakeDocument:
    def __init__(self, name="X-C3D.dwg", layers=("0", "C-ROAD")):
        self.Name, self.Path, self.Saved = name, "D:\\drawings", True
        self.Layers = FakeLayers(layers)
        self.ActiveLayer = self.Layers.Item("0")
        self.ModelSpace = FakeModelSpace(self)
        self.commands, self.regens = [], 0

    def Regen(self, which):
        self.regens += 1

    def HandleToObject(self, handle):
        for e in self.ModelSpace.items + self.Layers.items:
            if e.Handle.upper() == str(handle).upper():
                return e
        raise Exception("Invalid handle")

    def SendCommand(self, text):
        self.commands.append(text)


class FakeDocuments:
    def __init__(self, docs):
        self.docs, self.added = docs, 0

    @property
    def Count(self):
        return len(self.docs)

    def Item(self, i):
        return self.docs[i]

    def Add(self):
        self.added += 1  # recorded so a test can prove the server never creates a drawing (0004)
        doc = FakeDocument(name=f"Drawing{self.added}.dwg")
        self.docs.append(doc)
        return doc


class FakeApp:
    Name, Version = "Autodesk Civil 3D 2027", "26.0s (LMS Tech)"

    def __init__(self, doc=None, empty=False):
        """empty=True is AutoCAD on its Start tab: no document at all."""
        self.Documents = FakeDocuments([] if empty else [doc or FakeDocument()])
        self._active = None if empty else self.Documents.docs[0]
        self.zoomed = 0

    @property
    def ActiveDocument(self):
        if self._active is None:
            raise Exception("No active document")
        return self._active

    @ActiveDocument.setter
    def ActiveDocument(self, doc):
        self._active = doc

    def open(self, doc):
        """The user opens a drawing."""
        self.Documents.docs.append(doc)
        self._active = doc

    def ZoomExtents(self):
        self.zoomed += 1


RPC_E_CALL_REJECTED = -2147418111
DISP_E_UNKNOWNNAME = -2147352570


class FakeOle:
    """A CDispatch's _oleobj_: GetIDsOfNames answers as AutoCAD's IDispatch does."""

    def __init__(self, owner):
        self.owner, self.probes = owner, 0

    def GetIDsOfNames(self, lcid, name):
        self.probes += 1
        if self.owner.__dict__["_busy_left"] > 0:
            raise pythoncom.com_error(RPC_E_CALL_REJECTED, "Call was rejected by callee.", None, None)
        if not hasattr(self.owner.__dict__["_target"], name):
            raise pythoncom.com_error(DISP_E_UNKNOWNNAME, "Unknown name.", None, None)
        return 1


class RacyDispatch:
    """pywin32's late-bound CDispatch while AutoCAD starts up or opens a drawing: AutoCAD rejects the name
    lookup (GetIDsOfNames), pywin32's dynamic __getattr__ swallows that and raises
    AttributeError('<object>.<name>'). The first `busy_for` lookups fail that way; a name the target lacks
    always fails, as a real missing property does."""

    def __init__(self, target, busy_for, username="AutoCAD.Application.26"):
        d = self.__dict__
        d["_target"], d["_busy_left"], d["_username_"], d["lookups"] = target, busy_for, username, 0
        d["_oleobj_"] = FakeOle(self)

    def __getattr__(self, attr):
        d = self.__dict__
        d["lookups"] += 1
        if d["_busy_left"] > 0:
            d["_busy_left"] -= 1
            raise AttributeError(f"{d['_username_']}.{attr}")
        if not hasattr(d["_target"], attr):
            raise AttributeError(f"{d['_username_']}.{attr}")
        return getattr(d["_target"], attr)
