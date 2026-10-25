---
title: "temp-files — autocad_mcp/temp_files.py, the self-cleaning temp folder"
type: module
updated: 2026-10-24
sources: [autocad_mcp/temp_files.py, tests/test_temp_files.py, setup_claude.ps1, tests/test_setup_prune.py]
related: [../decisions/0003-no-writes-under-acc-or-beside-scripts.md, ../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md, scripts.md]
tags: [module, logs, temp]
---

# temp-files: `autocad_mcp/temp_files.py`

This repo's implementation of root decision
[0031](../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md) §2–4. A Cemengal-only file.

```python
from autocad_mcp.temp_files import TempFolder

log = TempFolder().log_path("diag")            # %TEMP%\Cemengal\AutocadMCP\diag-20261024.log
shots = TempFolder().artefact_dir("Screenshots")  # %TEMP%\Cemengal\AutocadMCP\Screenshots\
```

| Member | Contract |
|---|---|
| `TempFolder(app="AutocadMCP", base=None, max_age_days=7, max_bytes=50 MB)` | `root = <base or tempfile.gettempdir()>\Cemengal\<app>`; `base` is for tests |
| `log_path(name, ext=".log", day=None)` | `root\<name>-yyyyMMdd<ext>`; creates `root`; the caller appends |
| `artefact_dir(kind)` | `root\<kind>\`, created |
| `prune(now=None)` | files older than `max_age_days` go, then the oldest until the total is under `max_bytes`; empty subfolders go; locked files are skipped; never raises |

- **Once per process.** The first `log_path` or `artefact_dir` for a root prunes it; a module-level set remembers
  the roots already pruned, so a second instance does not prune again. No background thread.
- **Refuses ACC.** A folder with an `ACCDocs` path segment raises `ValueError` before anything is created.
- **PowerShell twin.** `setup_claude.ps1` cannot import it (the `.venv` may not exist yet), so it has
  `Invoke-CemTempPrune` with the same rules; `tests/test_setup_prune.py` runs it.

Tests: `tests/test_temp_files.py` (location, daily names, artefact folder, age and size pruning, locked files,
never raising, once per process, ACC refusal).
