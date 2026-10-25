"""Guard for root decision 0031 and docs/decisions/0003: no code of ours writes under ACC (a path with an
ACCDocs segment) or derives a write path from its own folder (__file__, $PSScriptRoot, %~dp0), because
that folder may itself be synced by the Desktop Connector. Reads from the own folder stay allowed."""
import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", ".git", "tests", "__pycache__", "docs", ".claude", ".agents", ".pytest_cache"}


def code_files(*suffixes):
    for path in sorted(REPO.rglob("*")):
        if path.suffix.lower() in suffixes and not SKIP_DIRS.intersection(path.relative_to(REPO).parts):
            yield path


def rel(path, base=REPO):
    return path.relative_to(base).as_posix()


# --- ACC paths --------------------------------------------------------------------------------------

ACC_PATH = re.compile(r"ACCDocs\s*[\\/]|[A-Za-z]:[\\/]+DC[\\/]", re.IGNORECASE)


def test_no_code_spells_a_path_under_acc():
    offenders = [f"{rel(p)}:{n}" for p in code_files(".py", ".ps1", ".bat", ".cmd")
                 for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
                 if ACC_PATH.search(line)]
    assert offenders == []


# --- Python: no write sink fed by a path derived from __file__ -------------------------------------

WRITE_CALLS = {"makedirs", "mkdir", "copy", "copy2", "copyfile", "copytree", "move", "FileHandler",
               "TimedRotatingFileHandler", "RotatingFileHandler"}
WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "touch"}


def mentions(node, names):
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))


def tainted_names(tree):
    """Names assigned, directly or through other names, from an expression that uses __file__."""
    names = {"__file__"}
    assigns = [n for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))]
    changed = True
    while changed:
        changed = False
        for a in assigns:
            if a.value is not None and mentions(a.value, names):
                targets = a.targets if isinstance(a, ast.Assign) else [a.target]
                for t in targets:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name) and n.id not in names:
                            names.add(n.id)
                            changed = True
    return names


def is_write_mode(call):
    mode = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "mode"), None)
    if mode is None:
        return False
    if not isinstance(mode, ast.Constant):
        return True  # unknown mode: assume it writes
    return any(c in str(mode.value) for c in "wax+")


def python_offenders(path, base=REPO):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    tainted = tainted_names(tree)
    found = []
    for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
        f = call.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if name == "open" and isinstance(f, ast.Name):
            hit = call.args and is_write_mode(call) and mentions(call.args[0], tainted)
        elif name == "open":  # Path.open(mode)
            hit = (call.args and isinstance(call.args[0], ast.Constant)
                   and any(c in str(call.args[0].value) for c in "wax+") and mentions(f.value, tainted))
        elif name in WRITE_METHODS and isinstance(f, ast.Attribute):
            hit = mentions(f.value, tainted)
        elif name in WRITE_CALLS:
            hit = any(mentions(a, tainted) for a in call.args)
        else:
            hit = False
        if hit:
            found.append(f"{rel(path, base)}:{call.lineno}")
    return found


def test_no_python_write_path_is_derived_from_its_own_folder():
    offenders = [o for p in code_files(".py") for o in python_offenders(p)]
    assert offenders == []


def test_the_python_guard_catches_the_old_pattern(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import os\n"
        "here = os.path.dirname(os.path.abspath(__file__))\n"
        "log = os.path.join(here, 'x_log.txt')\n"
        "open(log, 'w').write('x')\n"
        "open(os.path.join(os.path.dirname(__file__), 'y.txt'), mode='a')\n"
        "open(os.path.join(here, 'readme.txt')).read()\n",
        encoding="utf-8")
    assert sorted(o.rsplit(":", 1)[1] for o in python_offenders(sample, base=tmp_path)) == ["4", "5"]


# --- PowerShell and batch: no write cmdlet or redirection into the script's own folder --------------

PS_SINK = re.compile(r"\b(Start-Transcript|Out-File|Set-Content|Add-Content|Export-\w+|Tee-Object|New-Item|"
                     r"Copy-Item|Move-Item)\b|(?<![<\d])>{1,2}(?!\s*\$null)", re.IGNORECASE)
PS_ASSIGN = re.compile(r"^\s*\$(\w+)\s*=(.*)$")


def powershell_offenders(path):
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    tainted = {"PSScriptRoot", "PSCommandPath"}
    for line in lines:  # one pass in file order is enough for straight-line scripts
        m = PS_ASSIGN.match(line)
        if m and any(re.search(rf"\${t}\b", m.group(2), re.IGNORECASE) for t in tainted):
            tainted.add(m.group(1))
    return [f"{rel(path)}:{n}" for n, line in enumerate(lines, 1)
            if not line.lstrip().startswith("#") and PS_SINK.search(line.split("#")[0])
            and any(re.search(rf"\${t}\b", line, re.IGNORECASE) for t in tainted)]


def batch_offenders(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [f"{rel(path)}:{n}" for n, line in enumerate(lines, 1)
            if re.search(r">{1,2}\s*\"?%~dp0", line, re.IGNORECASE)]


def test_no_script_writes_into_its_own_folder():
    offenders = [o for p in code_files(".ps1") for o in powershell_offenders(p)]
    offenders += [o for p in code_files(".bat", ".cmd") for o in batch_offenders(p)]
    assert offenders == []


def test_setup_refuses_an_acc_folder_before_it_writes_anything():
    lines = (REPO / "setup_claude.ps1").read_text(encoding="utf-8-sig").splitlines()
    refusal = next((n for n, l in enumerate(lines) if "ACCDocs" in l and "throw" in l), None)
    first_write = next(n for n, l in enumerate(lines)
                       if re.search(r"Start-Transcript|-m\"?,?\s*\"?venv|pip install|New-Item|Set-Content", l))
    assert refusal is not None and refusal < first_write
