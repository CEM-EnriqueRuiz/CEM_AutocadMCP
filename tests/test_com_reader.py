"""docs/decisions/0006: the export reads COM through ComReader, which looks each property name up once per
object type (a DISPID cache) and Invokes it on the raw IDispatch, instead of pywin32's late binding that asks
AutoCAD for the type info and the name on every object. A busy AutoCAD is waited for, within a patience."""
import pythoncom
import pytest

from autocad_mcp.export import Busy, ComReader, Unavailable
from autocad_mcp.server import is_busy

RPC_E_CALL_REJECTED = -2147418111
DISP_E_UNKNOWNNAME = -2147352570


class FakeIDispatch:
    """The raw IDispatch of a fake COM object: counts name lookups and invokes, like a round trip each."""
    names = {}

    def __init__(self, target, log, busy=0):
        self.target, self.log, self.busy = target, log, busy

    def GetIDsOfNames(self, lcid, name):
        self.log.append(("ids", name))
        if not hasattr(self.target, name):
            raise pythoncom.com_error(DISP_E_UNKNOWNNAME, "Unknown name.", None, None)
        return self.names.setdefault(name, len(self.names) + 1)

    def Invoke(self, dispid, lcid, flags, want, *args):
        self.log.append(("invoke", dispid))
        if self.busy > 0:
            self.busy -= 1
            raise pythoncom.com_error(RPC_E_CALL_REJECTED, "Call was rejected by callee.", None, None)
        name = next(n for n, i in self.names.items() if i == dispid)
        value = getattr(self.target, name)
        if flags == pythoncom.DISPATCH_METHOD:
            value = value(*args)
        if hasattr(value, "ObjectName") or hasattr(value, "Item"):
            return FakeIDispatch(value, self.log)
        return value


class Thing:
    def __init__(self, **props):
        self.__dict__.update(props)


def reader(**kwargs):
    kwargs.setdefault("wait", 0)
    return ComReader(is_busy, raw_types=(FakeIDispatch,), **kwargs)


def test_a_property_name_is_looked_up_once_per_type():
    log = []
    a = FakeIDispatch(Thing(ObjectName="AcDbLine", Layer="0"), log)
    b = FakeIDispatch(Thing(ObjectName="AcDbLine", Layer="GEOM"), log)
    r = reader()
    assert [r.get(o, "Layer", kind="AcDbLine") for o in (a, b)] == ["0", "GEOM"]
    assert log.count(("ids", "Layer")) == 1 and sum(1 for k, _ in log if k == "invoke") == 2


def test_methods_and_objects_stay_raw():
    log = []
    inner = Thing(ObjectName="AcDbCircle", Radius=2.0)
    space = FakeIDispatch(Thing(Item=lambda i: inner, Count=1), log)
    r = reader()
    circle = r.call(space, "Item", 0, kind="Block")
    assert isinstance(circle, FakeIDispatch)
    assert r.get(circle, "Radius", kind="AcDbCircle") == 2.0


def test_an_unknown_name_is_unavailable_and_not_asked_again():
    log = []
    r = reader()
    obj = FakeIDispatch(Thing(ObjectName="AcDbViewport"), log)
    for _ in range(2):
        with pytest.raises(Unavailable):
            r.get(obj, "ViewCenter", kind="AcDbViewport")
    assert log.count(("ids", "ViewCenter")) == 1


def test_a_busy_autocad_is_waited_for():
    log, waits = [], []
    obj = FakeIDispatch(Thing(Name="Model"), log, busy=3)
    r = reader(on_wait=lambda: waits.append(1))
    assert r.get(obj, "Name", kind="Layout") == "Model"
    assert len(waits) == 3 and r.busy_waits == 3


def test_patience_ends_a_wait_with_busy():
    obj = FakeIDispatch(Thing(Name="Model"), [], busy=10 ** 6)
    r = reader(patience=0.0)
    with pytest.raises(Busy):
        r.get(obj, "Name", kind="Layout")


def test_a_checkpoint_can_stop_a_wait():
    class Stop(Exception):
        pass

    def checkpoint():
        raise Stop()

    obj = FakeIDispatch(Thing(Name="Model"), [], busy=10 ** 6)
    with pytest.raises(Stop):
        reader(checkpoint=checkpoint).get(obj, "Name", kind="Layout")


def test_plain_python_objects_are_read_with_getattr():
    r = reader()
    obj = Thing(Radius=1.5, GetBulge=lambda i: i * 0.5)
    assert r.get(obj, "Radius") == 1.5 and r.call(obj, "GetBulge", 2) == 1.0
    with pytest.raises(Unavailable):
        r.get(obj, "Center")
