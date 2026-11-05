---
title: "0003 — Nothing writes under ACC or beside its script; logs go to a self-cleaning temp folder"
type: decision
status: current
updated: 2026-11-05
sources: [https://github.com/CEMENGAL/CEM_Workspace/issues/5, "the user, 2026-10-24: no logs or other files in an ACC path; logs in a local temp folder that cleans itself", "the user, 2026-10-25: only the MCPs were in question; they are strict", https://github.com/CEM-EnriqueRuiz/CEM_API/issues/82, autocad_mcp/temp_files.py, setup_claude.ps1, diag_com.py, live_test.py, tests/test_no_acc_writes.py, tests/test_temp_files.py, tests/test_setup_prune.py]
related: [../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md, ../modules/temp-files.md, ../modules/scripts.md, 0004-reads-never-modify-the-drawing.md]
tags: [acc, logs, temp, guard]
---

# 0003 — Nothing writes under ACC or beside its script; logs go to a self-cleaning temp folder

## Context

Root decision [0031](../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md): the
Desktop Connector syncs every file under `C:\DC\ACCDocs` to every colleague, and a tool's own folder may be on
ACC. Since 2026-10-25 0031 holds the MCPs to the rule with no exception (only add-ins keep team files they write by
design); this repo is an MCP server, so it has none. The audit of 2026-10-24 found in this repo:

| Writer | What | Kind | Before | Now |
|---|---|---|---|---|
| `autocad_mcp/server.py` | nothing | — | stdio only; stderr goes to Claude Desktop's own log | unchanged |
| `diag_com.py` | `diag_log.txt` | dev log | beside the script (`__file__`) | `%TEMP%\Cemengal\AutocadMCP\diag-yyyyMMdd.log`, appended |
| `live_test.py` | `live_test_log.txt` | dev log | beside the script (`__file__`) | `%TEMP%\Cemengal\AutocadMCP\live-test-yyyyMMdd.log`, appended |
| `setup_claude.ps1` | `setup_log.txt` (transcript) | dev log | beside the script (`$PSScriptRoot`) | `%TEMP%\Cemengal\AutocadMCP\setup-yyyyMMdd.log`, appended |
| `setup_claude.ps1` | `claude_desktop_config.json` + `.bak-autocad` | Claude's per-user settings | local app data | unchanged (settings, not ACC, not beside the script) |
| `setup_claude.ps1` | `.venv\` | the install | the repo folder | unchanged; refuses to run in an ACC folder |
| Python | `autocad_mcp\__pycache__\` | interpreter cache | beside the modules | unchanged; local repo, ignored by git |

## Decision

1. **One helper, `autocad_mcp.temp_files.TempFolder`**, with 0031's contract: `log_path(name)` gives
   `%TEMP%\Cemengal\AutocadMCP\<name>-yyyyMMdd.log` (or `.jsonl`), `artefact_dir(kind)` gives
   `%TEMP%\Cemengal\AutocadMCP\<Kind>\`. The first of either call in a process prunes the folder: files older than
   7 days, then the oldest until it is under 50 MB; locked files are skipped; pruning never raises. A root under
   an `ACCDocs` segment raises `ValueError`. [Module page](../modules/temp-files.md).
   **Amended 2026-11-01 for `exports\`** ([0006](0006-background-export-jobs.md)): the newest export file (`.json` or `.failed.json`) and the newest complete `.json` are never pruned; the
   others stay up to 3 files in all, and only while under 7 days old (whichever keeps fewer); a `.json.partial`
   stays while under 7 days old; `exports\` is outside the 50 MB cap of the rest of the folder.
2. **The scripts log there, appending one block per run** with a timestamp header, and print the log's path.
3. **`setup_claude.ps1` carries the same prune in PowerShell** (`Invoke-CemTempPrune`, between `# >>> prune`
   and `# <<< prune`), because its transcript starts before the `.venv`, and so the Python helper, exists;
   it applies the same exports rule. `tests/test_setup_prune.py` runs that block against a scratch folder.
4. **`setup_claude.ps1` refuses an ACC folder** before it writes anything: a `.venv` there is thousands of files
   synced to every colleague.
5. **Guard, `tests/test_no_acc_writes.py`:** fails when code spells a path under ACC, when a Python write call
   (`open` in a write mode, `write_text`, `mkdir`, `makedirs`, `shutil.copy*`, a logging `FileHandler`) takes a
   path derived from `__file__`, when a PowerShell write cmdlet or redirection uses `$PSScriptRoot`, or a batch
   redirection uses `%~dp0`, and when the setup's ACC refusal is missing or comes after its first write.
6. **The prune follows no reparse point** (SEC-1, CWE-59, 2026-11-01): it never enters, lists or deletes through a
   junction, a symlink or any other reparse point, at the root, its `Cemengal` parent, `exports\`, any subfolder
   or any file, and re-checks the chain from the root's parent down to a file just before deleting it. Other
   accounts (the Codex sandbox ones) have Modify on `%TEMP%\Cemengal\AutocadMCP` on this machine; a junction there
   made the old `rglob` delete the user's files outside it. Both twins, as the workspace's C# `CemTempFolder.FilesUnder`.
   `tests/test_prune_reparse.py` puts a junction at each of those places, for both twins. Rejected: resolving
   paths and comparing them to the root (a junction swapped in between the check and the delete still wins;
   skipping reparse points is what the C# twin does).
   **The writes too** (the architect, 2026-11-01): `_prepare`, behind `log_path` and `artefact_dir`, raises
   `ValueError("Refusing to write through a junction or link: …")` when `Cemengal`, the root or the artefact folder
   is a reparse point, before the prune and again after `mkdir`; `ExportJobs.start` turns it into the tool's
   error. `setup_claude.ps1` does the same for its transcript: `Assert-CemWritableTemp` (inside the prune block)
   throws before the prune and again after `New-Item`, both before `Start-Transcript`, so setup stops with the
   reason. The race left is [known gap](../concepts/known-gaps.md) 17.

**Rejected:**
- Writing the dev logs nowhere (console only): the user runs the `.bat` files by double-click and hands the log
  to an agent; a file is the point.
- `PYTHONDONTWRITEBYTECODE` or `PYTHONPYCACHEPREFIX` in the Claude config to stop `__pycache__`: the repo is a
  local git checkout and the setup refuses ACC, so the cache never reaches ACC; it would also mean editing the
  user's Claude config for no observed problem. Revisit if the server is ever shipped from ACC.
- Calling the Python helper from `setup_claude.ps1`: the transcript has to start before the `.venv` exists.

## Consequences

- The three old logs beside the scripts (`diag_log.txt`, `live_test_log.txt`, `setup_log.txt`, written
  2026-10-17/18) stay where they are, untracked and ignored by `.gitignore`, for the user to delete. Superseded
  2026-11-05 by root [0037](../../../../docs/decisions/0037-code-follows-the-tables.md) (nothing temporary stays in a
  repo): the maintenance review moved them out and dropped their `.gitignore` lines ([known gaps](../concepts/known-gaps.md) 11).
- A future tool that writes an artefact (a screenshot, an export) uses `TempFolder().artefact_dir(kind)`.
- The guard is static, so a new write form it does not know (for example a new library writer) needs a line
  in the test.
