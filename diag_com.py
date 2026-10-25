r"""Diagnose why GetActiveObject('AutoCAD.Application') fails.
Logs to %TEMP%\Cemengal\AutocadMCP\diag-yyyyMMdd.log (Cemengal: never beside this script, docs/decisions/0003)."""
import sys, os, winreg, ctypes
from datetime import datetime
import pythoncom, win32com.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autocad_mcp.temp_files import TempFolder
out = []
def p(*a): out.append(" ".join(str(x) for x in a))
p("python", sys.version, "admin:", bool(ctypes.windll.shell32.IsUserAnAdmin()))
def reg(path, name=""):
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError as e:
        return f"<missing: {e.strerror}>"
p("AutoCAD.Application CLSID:", reg(r"AutoCAD.Application\CLSID"))
p("AutoCAD.Application CurVer:", reg(r"AutoCAD.Application\CurVer"))
progids = []
with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root:
    i = 0
    while True:
        try: n = winreg.EnumKey(root, i)
        except OSError: break
        if n.lower().startswith("autocad.application"): progids.append(n)
        i += 1
for pid in progids:
    p("ProgID", pid, "->", reg(pid + r"\CLSID"))
p("--- Running Object Table")
try:
    rot = pythoncom.GetRunningObjectTable(); ctx = pythoncom.CreateBindCtx(0)
    for m in rot:
        try: p("ROT:", m.GetDisplayName(ctx, None))
        except Exception as e: p("ROT entry (name error)", e)
except Exception as e:
    p("ROT error", e)
p("--- GetActiveObject attempts")
for pid in ["AutoCAD.Application"] + progids:
    try:
        a = win32com.client.GetActiveObject(pid)
        p("OK", pid, a.Name, a.Version, a.ActiveDocument.Name)
    except Exception as e:
        p("FAIL", pid, e)
p("--- tasklist acad")
p(os.popen('tasklist /v /fi "imagename eq acad.exe"').read())
log = TempFolder().log_path("diag")
with open(log, "a", encoding="utf-8") as f:
    f.write(f"=== {datetime.now():%Y-%m-%d %H:%M:%S}\n" + "\n".join(out) + "\n")
print("\n".join(out))
print("Log:", log)
