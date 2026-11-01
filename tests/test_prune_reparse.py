"""SEC-1 (CWE-59): the prune never follows, and never deletes through, a reparse point (a junction or a symlink).

Other accounts can have Modify on %TEMP%\\Cemengal\\AutocadMCP (the Codex sandbox accounts, 2026-11-01): a junction
there, as a subfolder, as exports\\ itself, as the root or its Cemengal parent, must never lead the prune to the
user's files outside the folder. Both twins are checked on the same layouts: TempFolder.prune and setup_claude.ps1's
Invoke-CemTempPrune. Junctions need no privilege (mklink /J); a file symlink needs one, so that case skips when the
machine refuses it."""
import os
import subprocess

import pytest

from autocad_mcp.temp_files import TempFolder
from test_setup_prune import POWERSHELL, run_prune
from test_temp_files import write


@pytest.fixture
def links():
    """Junctions made by a test, removed (the link only, never its target) when it ends."""
    made = []

    def junction(link, target):
        link.parent.mkdir(parents=True, exist_ok=True)
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
        made.append(link)
        return link

    yield junction
    for link in reversed(made):
        try:
            os.rmdir(link)  # removes a junction, not what it points to
        except OSError:
            pass


def victims(folder):
    """The user's files outside the temp folder: old, large and export-like, so every rule would take them."""
    return [write(folder / "notes.log", 100, 30), write(folder / "big.bin", 1000, 1),
            *[write(folder / f"drawing{i}.json", 10, 10 + i) for i in range(5)],
            write(folder / "job.json.partial", 10, 30), write(folder / "deep" / "old.txt", 10, 30)]


def layouts(base, links):
    """(prune root, the user's files) for each place a junction can appear."""
    root = base / "Cemengal" / "AutocadMCP"
    yield "subfolder", root, root / "linked"
    yield "nested subfolder", root, root / "Kind" / "deep" / "linked"
    yield "exports", root, root / "exports"
    yield "root", root, root
    yield "Cemengal parent", root, base / "Cemengal"


CASES = ["subfolder", "nested subfolder", "exports", "root", "Cemengal parent"]


def build(tmp_path, links, case):
    base = tmp_path / "temp"
    for name, root, link in layouts(base, links):
        if name == case:
            outside = tmp_path / "outside"
            target = outside / "AutocadMCP" if case == "Cemengal parent" else outside
            mine = victims(target)
            links(link, outside if case == "Cemengal parent" else target)
            own = None
            if case in ("subfolder", "nested subfolder", "exports"):
                own = write(root / "old-own.log", 10, 30)  # the folder's own stale file is still pruned
            return base, root, mine, own


@pytest.mark.parametrize("case", CASES)
def test_the_python_prune_follows_no_junction(tmp_path, links, case):
    base, root, mine, own = build(tmp_path, links, case)
    folder = TempFolder("AutocadMCP", base=base, max_bytes=50)
    folder.prune()
    folder.prune_exports()
    assert [p.name for p in mine if not p.exists()] == []
    if own is not None:
        assert not own.exists()


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
@pytest.mark.parametrize("case", CASES)
def test_the_setup_prune_follows_no_junction(tmp_path, links, case):
    base, root, mine, own = build(tmp_path, links, case)
    run_prune(root, max_bytes=50)
    assert [p.name for p in mine if not p.exists()] == []
    if own is not None:
        assert not own.exists()


def file_symlink(link, target):
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip("this machine refuses file symlinks without the privilege")
    return link


def test_a_file_symlink_is_neither_followed_nor_deleted(tmp_path):
    folder = TempFolder("AutocadMCP", base=tmp_path / "temp")
    target = write(tmp_path / "outside" / "precious.json", 10, 30)
    link = file_symlink(folder.root / "exports" / "link.json", target)
    write(folder.root / "exports" / "a.json", 10, 0.1)
    folder.prune()
    assert target.exists() and os.path.lexists(link)


# --- the writes: _prepare refuses a junctioned root, Cemengal parent or artefact folder (known gap 17, part 2) ---

WRITES = [("root", lambda f: f.log_path("diag")), ("Cemengal parent", lambda f: f.log_path("diag")),
          ("exports", lambda f: f.artefact_dir("exports"))]


@pytest.mark.parametrize("case, write_call", WRITES, ids=[w[0] for w in WRITES])
def test_no_write_goes_through_a_junction(tmp_path, links, case, write_call):
    base, outside = tmp_path / "temp", tmp_path / "outside"
    root = base / "Cemengal" / "AutocadMCP"
    link = {"root": root, "Cemengal parent": base / "Cemengal", "exports": root / "exports"}[case]
    if case == "exports":
        root.mkdir(parents=True)
    links(link, outside)
    before = sorted(p.relative_to(outside) for p in outside.rglob("*"))
    with pytest.raises(ValueError, match="junction or link"):
        write_call(TempFolder("AutocadMCP", base=base))
    assert sorted(p.relative_to(outside) for p in outside.rglob("*")) == before  # nothing created through it


def test_export_drawing_fails_with_the_reason_instead_of_writing(tmp_path, links):
    from autocad_mcp.export import ExportJobs, Limits
    from export_drawing_fake import drawing_with_everything
    base, outside = tmp_path / "temp", tmp_path / "outside"
    links(base / "Cemengal" / "AutocadMCP", outside)
    app, doc, _ = drawing_with_everything()
    jobs = ExportJobs(temp=TempFolder("AutocadMCP", base=base))
    result = jobs.start(app, doc.Name, doc.FullName, Limits())
    assert "junction or link" in result["error"] and not result.get("success")
    assert list(outside.iterdir()) == [] and jobs.jobs == {}


# --- setup_claude.ps1's transcript: the same rule as _prepare (known gap 17) -----------------------------------

def run_assert(root, folder=""):
    from test_setup_prune import prune_function
    script = prune_function() + f"\nAssert-CemWritableTemp -Dir '{root}' -Folder '{folder}'\n"
    return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=60)


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
@pytest.mark.parametrize("case", ["root", "Cemengal parent", "folder"])
def test_setup_refuses_to_write_through_a_junction(tmp_path, links, case):
    base, outside = tmp_path / "temp", tmp_path / "outside"
    root = base / "Cemengal" / "AutocadMCP"
    folder = root / "exports"
    if case == "folder":
        root.mkdir(parents=True)
    links({"root": root, "Cemengal parent": base / "Cemengal", "folder": folder}[case], outside)
    run = run_assert(root, folder if case == "folder" else "")
    assert run.returncode != 0 and "junction or link" in (run.stdout + run.stderr)


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_writes_to_a_plain_temp_folder(tmp_path):
    root = tmp_path / "temp" / "Cemengal" / "AutocadMCP"
    root.mkdir(parents=True)
    assert run_assert(root).returncode == 0


def test_setup_checks_before_and_after_making_the_folder_and_before_the_transcript():
    from test_setup_prune import SCRIPT
    body = SCRIPT.read_text(encoding="utf-8-sig").split("# <<< prune", 1)[1]
    first, made, second, transcript = (body.index(s) for s in (
        "Assert-CemWritableTemp -Dir $logDir", "New-Item -ItemType Directory -Force $logDir",
        "Assert-CemWritableTemp -Dir $logDir", "Start-Transcript"))
    second = body.index("Assert-CemWritableTemp -Dir $logDir", made)
    assert first < body.index("Invoke-CemTempPrune -Dir $logDir") < made < second < transcript


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_checks_a_root_given_with_a_trailing_backslash(tmp_path, links):
    root = tmp_path / "temp" / "Cemengal" / "AutocadMCP"
    links(root, tmp_path / "outside")
    run = run_assert(str(root) + "\\")
    assert run.returncode != 0 and "junction or link" in (run.stdout + run.stderr)
