---
title: "temp-files — autocad_mcp/temp_files.py, the self-cleaning temp folder"
type: module
updated: 2026-11-01
sources: [autocad_mcp/temp_files.py, tests/test_temp_files.py, tests/test_export_jobs.py, setup_claude.ps1, tests/test_setup_prune.py]
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
| `TempFolder(app="AutocadMCP", base=None, max_age_days=7, max_bytes=50 MB, max_exports=3)` | `root = <base or tempfile.gettempdir()>\Cemengal\<app>`; `base` is for tests |
| `log_path(name, ext=".log", day=None)` | `root\<name>-yyyyMMdd<ext>`; creates `root`; the caller appends |
| `artefact_dir(kind)` | `root\<kind>\`, created |
| `prune(now=None)` | outside `exports\`: files older than `max_age_days` go, then the oldest until the total is under `max_bytes`; then `prune_exports`; empty subfolders go; locked files are skipped; never raises |
| `prune_exports(now=None)` | `exports\` by its own rule (below); also run by each finished export job; never raises |

- **Once per process.** The first `log_path` or `artefact_dir` for a root prunes it; a module-level set remembers
  the roots already pruned, so a second instance does not prune again. No background thread.
- **Refuses ACC.** A folder with an `ACCDocs` path segment raises `ValueError` before anything is created.
- **PowerShell twin.** `setup_claude.ps1` cannot import it (the `.venv` may not exist yet), so it has
  `Invoke-CemTempPrune` with the same rules, the exports rule included; `tests/test_setup_prune.py` runs it.
- **No reparse point** (SEC-1): `_walk` (`os.scandir`, `stat(follow_symlinks=False)`) neither lists nor enters a
  junction or symlink; `_safe_root` refuses a root or `Cemengal` parent that is one; `_delete` re-checks every
  component from the root's parent down to the file. `is_reparse(path)` counts an unreadable path as one.
  `_prepare` (behind `log_path` and `artefact_dir`) raises `ValueError` when `Cemengal`, the root or the artefact
  folder is one, before the prune and again after `mkdir`: nothing is written through a junction.
  `setup_claude.ps1`'s `Assert-CemWritableTemp` is its twin for the setup transcript.
  **Check, for any change here:** the prune follows no reparse point and no write goes through one
  (`tests/test_prune_reparse.py`, both twins for the prune).
- **`exports\` has its own rule** (2026-11-01, [0006](../decisions/0006-background-export-jobs.md), known gap 16
  closed): the newest export file (`.json` or `.failed.json`) and the newest complete `.json` are never pruned; the
  others stay up to 3 files in all, and only while under 7 days old (whichever keeps fewer); a `.json.partial`
  stays while under 7 days old; `exports\` is outside the 50 MB cap of the rest of the folder. A 50 MB export of a real drawing had been
  deleted by the size cap at the next server start.

Users: the scripts' logs, and `export_drawing`'s files in `artefact_dir("exports")`
([export](export.md)), kept by the exports rule above.

Tests: `tests/test_temp_files.py` (location, daily names, artefact folder, age and size pruning, locked files,
never raising, once per process, ACC refusal).
