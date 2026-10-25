"""setup_claude.ps1 writes its transcript to %TEMP%\\Cemengal\\AutocadMCP before the .venv (and so the Python
helper) exists, so it carries its own prune with the TempFolder contract (root decision 0031 §4). This runs
that function, cut out of the script, against a scratch folder."""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "setup_claude.ps1"
DAY = 24 * 3600
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def prune_function():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    match = re.search(r"# >>> prune\r?\n(.*?)# <<< prune", text, re.DOTALL)
    assert match, "setup_claude.ps1 has no '# >>> prune' ... '# <<< prune' block"
    return match.group(1)


def write(path, size, age_days):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    stamp = time.time() - age_days * DAY
    os.utime(path, (stamp, stamp))
    return path


def run_prune(folder, max_bytes):
    script = prune_function() + f"\nInvoke-CemTempPrune -Dir '{folder}' -MaxBytes {max_bytes}\n"
    subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script], check=True, timeout=60)


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_prune_follows_the_temp_folder_contract(tmp_path):
    old = write(tmp_path / "setup-20261001.log", 10, age_days=8)
    old_kind = write(tmp_path / "Kind" / "a.png", 10, age_days=20)
    oldest_recent = write(tmp_path / "a.log", 100, age_days=3)
    newer = write(tmp_path / "b.log", 100, age_days=2)
    newest = write(tmp_path / "c.log", 100, age_days=1)
    locked = write(tmp_path / "locked.log", 10, age_days=9)
    with open(locked, "rb"):
        run_prune(tmp_path, max_bytes=250)
    assert not old.exists() and not old_kind.exists()
    assert not oldest_recent.exists()
    assert newer.exists() and newest.exists()
    assert locked.exists()


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_prune_never_throws_on_a_missing_folder(tmp_path):
    run_prune(tmp_path / "missing", max_bytes=1)


def claude_configs(local, roaming):
    text = SCRIPT.read_text(encoding="utf-8-sig")
    match = re.search(r"# >>> configs\r?\n(.*?)# <<< configs", text, re.DOTALL)
    assert match, "setup_claude.ps1 has no '# >>> configs' ... '# <<< configs' block"
    script = match.group(1) + f"\nGet-ClaudeConfigs -LocalAppData '{local}' -AppData '{roaming}' | % {{ $_ }}\n"
    run = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
                         check=True, timeout=60, capture_output=True, text=True)
    return [Path(line) for line in run.stdout.splitlines() if line.strip()]


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_finds_the_claude_data_config_of_the_current_msix_app(tmp_path):
    r"""Since 2026-10-20 Claude Desktop keeps its config in %LOCALAPPDATA%\Claude-Data\claude_<id>\; the old
    Packages\Claude_<id>\LocalCache\Roaming\Claude folder only holds a .user-data-left marker."""
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    current = write(local / "Claude-Data" / "claude_abc" / "claude_desktop_config.json", 2, 0)
    (local / "Packages" / "Claude_abc" / "LocalCache" / "Roaming" / "Claude").mkdir(parents=True)
    assert claude_configs(local, roaming) == [current]


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_still_finds_the_older_installs(tmp_path):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    msix = write(local / "Packages" / "Claude_abc" / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json", 2, 0)
    classic = write(roaming / "Claude" / "claude_desktop_config.json", 2, 0)
    assert sorted(claude_configs(local, roaming)) == sorted([msix, classic])


@pytest.mark.skipif(POWERSHELL is None, reason="needs Windows PowerShell")
def test_setup_creates_the_classic_config_when_there_is_none(tmp_path):
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    assert claude_configs(local, roaming) == [roaming / "Claude" / "claude_desktop_config.json"]
