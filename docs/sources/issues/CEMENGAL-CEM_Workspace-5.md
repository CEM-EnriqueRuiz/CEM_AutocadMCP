---
title: "CEMENGAL/CEM_Workspace#5: export_drawing, the exports prune rule, the reparse-point guards"
type: source
updated: 2026-11-01
sources: [https://github.com/CEMENGAL/CEM_Workspace/issues/5, "the architect's brief of 2026-11-01 (run_4ac88c3583b1)", "the coordinator's answers of 2026-11-01", "the QA and security quick reviews and rechecks of 2026-11-01", autocad_mcp/export.py, autocad_mcp/export_text.py, autocad_mcp/server.py, autocad_mcp/temp_files.py, setup_claude.ps1, tests/]
related: [../../index.md, ../../decisions/0003-no-writes-under-acc-or-beside-scripts.md, ../../decisions/0006-background-export-jobs.md, ../../modules/export.md, ../../modules/temp-files.md, ../../concepts/export-schema.md, ../../concepts/known-gaps.md, ../../workflows/live-test.md, ../../workflows/test.md, ../commits/2026-11.md]
tags: [issue, export, prune, reparse, security, cross-repo]
---

# CEMENGAL/CEM_Workspace#5

**Issue:** https://github.com/CEMENGAL/CEM_Workspace/issues/5, the umbrella issue the user chose for the 2026-11-01 MCP modeller work across the workspace.
This page is this repo's part: a complete, read-only background export of a drawing (`export_drawing`,
`get_export_status`, `cancel_export`), the exports prune rule, the reparse-point guards of the temp folder, and the
review findings. Committed as one commit on `main`, 2026-11-01, not pushed (the architect pushes).

## End state

| Finding | Severity | End state |
|---|---|---|
| Known gap 16: an export over 50 MB was pruned at the next start | — | closed: `exports\` keeps its own rule ([0006](../../decisions/0006-background-export-jobs.md) point 5) |
| SEC-1: the prune followed junctions (CWE-59) | High, blocking | closed in both twins, prune and writes ([0003](../../decisions/0003-no-writes-under-acc-or-beside-scripts.md) point 6) |
| QA-1: the Python exports rule kept an old second complete export | Medium | closed; both twins agree |
| QA-4: the COM stream leaked when an export was refused | Info | closed (`AppOpener`) |
| QA-6 / SEC-6: no tests for hostile names, junctions, the QA-1 rule | test gaps | closed |
| Known gap 17: writes through a junctioned temp folder | — | closed for Python and the setup transcript; the check-to-act race stays open, narrowed ([known gaps](../../concepts/known-gaps.md) 17) |
| QA-8: a long drawing name exceeded 260 characters | Low | closed (bounded, hashed stem) |
| SEC-11: SHA-1 without `usedforsecurity=False` | Info | closed |

Both reviews end at 0 open blocking findings. **Tests:** 196 passed, 1 skipped (a file symlink needs a privilege on
this machine), 57 before this work. **Live:** plain AutoCAD 2025, a real drawing the user opened (names and contents
kept out of this wiki), 68,798 entities at 685–795 entities/s, read only ([live test](../../workflows/live-test.md)).
Phase 2 (an in-process AutoLISP reader) stays parked until the pilot shows whether the computed architectural
texts are exact enough.

## The record

**Asked:** the architect's brief, from the user: «¿por qué tú no puedes crear las herramientas en el MCP de
autocad que te permitan hacer todo lo que hacía CODEX?», then «sí, arranca los dos agentes». A modelling agent
needs every dimension's written text, the views by their supplier names, the blocks and attributes of a drawing.

**The plan, approved by the coordinator before any edit**, with these answers:
- build v1 on COM now, with the DISPID cache; record what ActiveX lacks (viewport view centre and frozen layers,
  dimension defining and dimension-line points, the rendered text) as `null` + `unavailable`, the displayed text
  as `computed`, architectural and fractional flagged approximate;
- the in-process route (an AutoLISP `entget` reader for dimensions and viewports) is decided after the live
  measurement, not built now; ObjectDBX from outside gives no speed, a .NET plugin is a plugin this repo lacks;
- splines exactly (control points, knots, weights, fit points);
- a failed or cancelled export keeps `<name>.failed.json` with the reason, never a plain `.json`;
- the temp folder's pruning is acceptable; the tool says exports are temporary;
- no live test now: AutoCAD is not running and `CEM_Test\MCP` is not on this machine; the coordinator will arrange
  a drawing with real dimensions, opened by the user, given by exact path. No commit.

Decisions, reasons and rejected alternatives: [0006](../../decisions/0006-background-export-jobs.md).

**Files:** `autocad_mcp/export.py`, `autocad_mcp/export_text.py` (new); `autocad_mcp/server.py` (three tools,
`self.exports`, each change marked `# Cemengal`); `tests/fake_acad.py` (layouts, paper spaces, block definitions,
a shared handle sequence, `writes`); `tests/export_drawing_fake.py`, `tests/test_export_text.py`,
`tests/test_export_schema.py`, `tests/test_export_jobs.py`, `tests/test_com_reader.py`,
`tests/test_com_reader_real.py` (new); `tests/test_tool_contract.py` (status and cancel answer an unknown job
without AutoCAD).

**Tests, red first:** the four new modules failed at collection (`ModuleNotFoundError: autocad_mcp.export_text`);
then the server tests failed on the missing `export_drawing` until the tools were wired. Now 140 passed (57 before).
The first draft of the real-COM marshalling test deadlocked: `Scripting.Dictionary` is in-process, so the worker
called back into the test thread blocked in `join`; the test now pumps messages, and the [export](../../modules/export.md)
page records why AutoCAD, out of process, does not need it.

**Setup:** this machine had no `.venv`; it was created with `C:\Python314\python.exe -m venv .venv` and
`pip install -e ".[dev]"` (ignored by git; `setup_claude.ps1` was not run, so Claude's config is untouched).

**Live, 2026-11-01**, after the coordinator's go (the user opened a real drawing in AutoCAD 2025 and the
coordinator named it by exact path; counts and timings only here, the JSON stayed in `%TEMP%`): 68,798 entities,
done in 100 s (685 entities/s), cancel in 0.5 s, the drawing unchanged ([live test](../../workflows/live-test.md)).
It showed two defects, fixed test-first the same hour (7 new tests, 147 in all): rotated dimensions have no
`ExtLine1Point`/`ExtLine2Point` in AutoCAD 2025 (the fake had them), and architectural text ignored
`SuppressZeroFeet`/`SuppressZeroInches`. The file is now compact JSON. Run 2: 795 entities/s, AutoCAD's
architectural shapes.

**Known gap 16, the architect's call of 2026-11-01:** an export must survive the prune at the next server start.
`exports\` got its own rule, outside the 50 MB cap: the newest export (and the newest complete `.json`) never
pruned, the others up to 3 files and 7 days. In `TempFolder.prune` / `prune_exports`, after each finished job,
and in `setup_claude.ps1`'s twin; the tool description says it. One reading made explicit: the newest complete
`.json` is kept with the newest file, so a failed retry never costs the last good export, and the total still
never exceeds 3. Test-first, 7 tests red then green (154 in all); a fresh process's prune of the real temp folder
kept the 50.0 MB export. Rejected: a larger cap in bytes. Phase 2 (AutoLISP) stays parked until the pilot shows
whether the computed architectural texts are exact enough.

**The QA and security quick reviews, fix batch of 2026-11-01** (0 Critical, 1 High; the user approved fixing the
Medium and Info findings too), test-first:
- **SEC-1, High (CWE-59), present at HEAD:** the prune followed junctions (`rglob` walked into one and saw the
  outside file). Both twins now skip reparse points everywhere and re-check before each delete
  ([0003](../../decisions/0003-no-writes-under-acc-or-beside-scripts.md) point 6). Red first: all 5 Python cases and 3
  of 5 PowerShell cases (Windows PowerShell 5.1's `-Recurse` already did not enter a subfolder junction, but the
  root, its parent and `exports\` were followed).
- **QA-1, Medium:** the Python prune kept an old second complete export when the newest was complete; now as the
  PowerShell twin. Red first in Python, green in PowerShell.
- **QA-4, Info:** `export_drawing` marshalled the COM stream before the job was accepted; now `start` marshals
  after its checks and releases the stream if the thread cannot start.
- **QA-6 / SEC-6, test gaps:** hostile drawing names (they already wrote inside `exports\`: green at once), the
  junction tests, the QA-1 rule.
- Left as [known gaps](../../concepts/known-gaps.md) 17: the check-to-delete race, and writes through a junctioned
  root. 183 passed, 1 skipped (file symlinks need a privilege on this machine).
- **Then, the architect:** close the writes too. `_prepare` refuses a junctioned `Cemengal`, root or artefact folder
  (the folder added to the asked root and parent: an `exports\` junction is the same hole), before the prune and
  after `mkdir`; `ExportJobs.start` returns "Cannot write the export: …". Red first (4 tests), 187 passed, 1 skipped.
  Known gap 17 keeps the race only.
- **Then the setup transcript** (the architect): `setup_claude.ps1` refuses the same before writing its
  transcript (`Assert-CemWritableTemp`, before the prune and after `New-Item`). Red first (5 tests); a sixth pins a
  root given with a trailing backslash, after a hand edit had left `TrimEnd('')`. 193 passed, 1 skipped.
- **QA-8, Low (the QA recheck; the user approved):** a valid drawing name over ~165 characters made the export path
  exceed 260 under the real `%TEMP%` (381 for a 300-character name), and `export_drawing` refused. `safe_stem` now
  bounds the stem to 80 characters: a readable prefix, `~` and a short SHA-1. Red first (3 tests: the stem, the
  path under the real `%TEMP%`, a 300-character export twice with no overwrite). 196 passed, 1 skipped.
- **SEC-11, Info (approved):** the SHA-1 in `safe_stem` is called with `usedforsecurity=False`, with a comment: it only
  tells two long names apart; never-overwrite rests on the `-2`/`-3` suffixes and the exclusive create. 196 passed, 1 skipped.
