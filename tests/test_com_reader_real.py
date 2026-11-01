"""docs/decisions/0006: ComReader's raw path and app_opener against a real COM object (Windows' Scripting.Dictionary),
so the pywin32 calls themselves (GetIDsOfNames, Invoke, marshalling into another apartment) are pinned without
AutoCAD. The fakes elsewhere cannot catch a wrong signature here."""
import threading

import pythoncom
import win32com.client

from autocad_mcp.export import ComReader, PyIDispatch, Unavailable, app_opener


def dictionary():
    d = win32com.client.Dispatch("Scripting.Dictionary")
    d.Add("a", 1)
    d.Add("b", 2)
    return d


def test_properties_and_methods_through_the_dispid_cache():
    d, r = dictionary(), ComReader()
    assert r.get(d, "Count", kind="Dictionary") == 2
    assert r.call(d, "Exists", "a", kind="Dictionary") is True
    assert r.call(d, "Keys", kind="Dictionary") == ("a", "b")
    assert set(r.ids) == {("Dictionary", "Count"), ("Dictionary", "Exists"), ("Dictionary", "Keys")}
    try:
        r.get(d, "NoSuchThing", kind="Dictionary")
        raise AssertionError("an unknown name must be Unavailable")
    except Unavailable:
        pass


def test_the_export_thread_gets_its_own_marshalled_proxy():
    d = dictionary()
    opener, seen = app_opener(d), {}

    def worker():
        pythoncom.CoInitialize()
        try:
            proxy = opener()
            seen["raw"] = isinstance(proxy, PyIDispatch)
            seen["count"] = ComReader().get(proxy, "Count", kind="Dictionary")
        finally:
            pythoncom.CoUninitialize()

    # The dictionary is in-process, so it lives in this thread's apartment and the worker's calls come back here:
    # pump messages while waiting. AutoCAD is out of process; there the worker's proxy calls acad.exe directly.
    t = threading.Thread(target=worker)
    t.start()
    for _ in range(1000):
        if not t.is_alive():
            break
        pythoncom.PumpWaitingMessages()
        t.join(0.01)
    assert seen == {"raw": True, "count": 2}
