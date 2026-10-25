---
title: "Test — the pytest suite and what it cannot cover"
type: workflow
updated: 2026-10-25
sources: [tests/, pyproject.toml, ../../docs/workflows/tdd-and-test-runner.md, ../../.claude/run-tests.ps1]
related: [live-test.md, ../modules/server.md, ../modules/temp-files.md, ../decisions/0003-no-writes-under-acc-or-beside-scripts.md]
tags: [test, pytest, tdd]
---

# Test

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"   # once: pytest into the .venv
.venv\Scripts\python.exe -m pytest -q                 # 57 tests, ~5 s, no AutoCAD needed
```

TDD is the default for new logic: a failing test first, read why it fails, then the code
([root workflow](../../../../docs/workflows/tdd-and-test-runner.md)). Windows only: the suite imports `pywin32`
and runs PowerShell.

| File | Pins |
|---|---|
| `test_temp_files.py` | `TempFolder`: location, daily names, artefact folder, pruning by age and size, locked files, never raising, once per process, ACC refusal ([0003](../decisions/0003-no-writes-under-acc-or-beside-scripts.md)) |
| `test_no_acc_writes.py` | the guard: no path under ACC, no write path from `__file__` / `$PSScriptRoot` / `%~dp0`, the setup's ACC refusal comes first; plus a self-test that it catches the old pattern |
| `test_setup_prune.py` | `setup_claude.ps1`'s `Invoke-CemTempPrune` and `Get-ClaudeConfigs`, cut out of the script and run in PowerShell against scratch folders |
| `test_reads_do_not_modify.py` | reads add no layer; a structure adds only its own layer ([0004](../decisions/0004-reads-never-modify-the-drawing.md)) |
| `test_time_budget.py` | layer cap, time budgets, no `Regen` on create, delete by handle without a scan and only in model space ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md)) |
| `test_tool_contract.py` | every listed tool reaches a method, no duplicate names, the handshake does not connect |
| `test_com_connection.py` | ProgID order, forced ProgID, stale generic ProgID, no launch, busy retry, following the active drawing ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md)) |
| `test_busy_race.py` | the startup/open race (`AttributeError` from pywin32's late binding) is retried while connecting and in `safe_operation`, within the budget; a missing property or a Python `AttributeError` is not ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md)) |
| `test_no_drawing.py` | on the Start tab every tool answers "No drawing is open in AutoCAD…" and none adds a document; a drawing opened later is found ([0004](../decisions/0004-reads-never-modify-the-drawing.md)) |

`tests/fake_acad.py` is an in-memory AutoCAD (application, documents, layers, model space, entities) that records
added layers, added documents, regens, `Item` calls and `Update`s; `FakeApp(empty=True)` is AutoCAD on its Start
tab, and `RacyDispatch` wraps a fake to fail its first name lookups as pywin32 does when AutoCAD is busy.
`conftest.py`'s `acad` fixture points the server's `GetActiveObject` at it.

**What it cannot cover:** real COM marshalling, AutoCAD's speed, its busy states, Civil 3D objects, the display.
Those are checked live through MCP ([live test](live-test.md)); a live run is not coverage, so pin what it
showed with a fake here.

A test that writes files uses `tmp_path`, never the current folder: a stub returning `Path()` once wrote the
pruning fixtures into the repo root (2026-10-24, removed the same minute).

The root runner runs the same suite: `D:\repos\Cemengal\.claude\run-tests.ps1 -Repos autocadmcp` (it expects the
`.venv` above).
