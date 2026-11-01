---
title: "0006 — A complete export runs as a background job, on COM, read only"
type: decision
status: current
updated: 2026-11-01
sources: [https://github.com/CEMENGAL/CEM_Workspace/issues/5, "the architect's brief of 2026-11-01 (run_4ac88c3583b1), the user: «¿por qué tú no puedes crear las herramientas en el MCP de autocad que te permitan hacer todo lo que hacía CODEX?»", "the coordinator's answers of 2026-11-01", autocad_mcp/export.py, autocad_mcp/export_text.py, tests/test_export_jobs.py, tests/test_export_schema.py, tests/test_com_reader.py, tests/test_com_reader_real.py, tests/test_export_text.py]
related: [0005-every-call-ends-inside-the-host-timeout.md, 0004-reads-never-modify-the-drawing.md, 0003-no-writes-under-acc-or-beside-scripts.md, ../modules/export.md, ../concepts/export-schema.md, ../concepts/com-connection.md, ../concepts/known-gaps.md]
tags: [export, jobs, threading, com, dimensions]
---

# 0006 — A complete export runs as a background job, on COM, read only

## Context

The user is building a modelling agent that turns supplier drawings into Revit equipment families. Its standard
says the **written dimension text always prevails**, and views keep the supplier's names (Vista A, Vista Z…).
The reads of 2026-11-01 could not serve it: model space only, a 40 s budget with truncation
([0005](0005-every-call-ends-inside-the-host-timeout.md)), no dimensions, layouts, viewports, MText, blocks or
attributes. Another agent (Codex, outside this workspace) had read all of it through PowerShell COM with no time
cap, so the data is reachable; what was missing is a tool that reads it all without breaking the host's 60 s or
hanging AutoCAD.

## Decision

1. **Three tools.** `export_drawing(document?, max_entities?, max_seconds?, max_bytes?, block_depth?)` starts a
   job and returns at once with `job_id` and the output path; `get_export_status(job_id)` gives the state
   (`running`, `done`, `failed`, `cancelled`), entities read and total per layout, elapsed time, speed, the paths
   and, on failure, the reason in one line; `cancel_export(job_id)` asks the job to stop. Each call ends in
   milliseconds, so 0005 holds for the tools while the walk itself has no 40 s budget.
2. **Its own thread and COM apartment.** The job runs on a `threading.Thread` that calls `CoInitialize`, and gets
   AutoCAD's `Application` through `CoMarshalInterThreadInterfaceInStream` from the server's connection
   (`app_opener`): COM objects belong to the apartment that made them, and a marshalled proxy to an
   out-of-process server calls `acad.exe` directly, so it is the same AutoCAD instance (`AppOpener`, marshalled
   only once the job is accepted; the thread uses the stream once, or it is released if the thread cannot start,
   QA-4), not a second
   `GetActiveObject` that could pick another one. AutoCAD serves one COM call at a time on its main thread and
   handles its UI between them: a long export can make it slower, never hung, and the server's other tools still
   answer.
3. **A DISPID cache (`ComReader`).** pywin32's late binding asks AutoCAD for the type info of every object it wraps
   and looks every name up again; the reader looks each name up once per object type (`(ObjectName, name)`) and
   then `Invoke`s on the raw `IDispatch`, which keeps objects raw too. A busy AutoCAD is waited for up to
   `busy_patience` (300 s), checking cancel and the time limit while it waits; beyond that the job fails.
4. **Read only** ([0004](0004-reads-never-modify-the-drawing.md)): properties, `Item`, `GetVariable`, `GetBulge`,
   `GetAttributes`, `GetText`, `GetLeaderLine*`. Never `Explode`, `Update`, `Regen`, `SendCommand`, `Save`.
5. **One file, temporary, never overwritten** ([0003](0003-no-writes-under-acc-or-beside-scripts.md)):
   `TempFolder().artefact_dir("exports")` / `<drawing>-yyyyMMdd-HHmmss.json`. The name is reserved by creating
   `<name>.json.partial` (`open(…, "x")`); a taken name moves to `-2`, `-3`…; the finished file is renamed into
   place with `os.rename`, which refuses to replace. **`exports\` keeps its own rule** (2026-11-01, the
   architect): the newest export file (`.json` or `.failed.json`) and the newest complete `.json` are never pruned; the
   others stay up to 3 files in all, and only while under 7 days old (whichever keeps fewer); a `.json.partial`
   stays while under 7 days old; `exports\` is outside the 50 MB cap of the rest of the folder. `TempFolder.prune` and
   `setup_claude.ps1`'s twin apply it at each start; each finished job applies it too (`prune_exports`). The tool
   description says so. The newest complete `.json` counts only when it is not already the newest file: a second,
   older complete export is kept only while under 7 days (QA-1, the two twins agree). No prune follows a reparse
   point ([0003](0003-no-writes-under-acc-or-beside-scripts.md) point 6).
   A drawing's name only gives the stem: `safe_stem` keeps `Path(name).stem` and replaces `<>:"/\|?*` and control
   characters, and the timestamp suffix rules out a bare device name; `..\`, absolute, UNC, stream, newline and
   `CON` names all write inside `exports\` (`tests/test_export_jobs.py`, QA-6 / SEC-6). A stem over `MAX_STEM` (80)
   characters keeps its first 71, then `~` and 8 hex characters of the SHA-1 of the whole stem (QA-8): the path
   stays under Windows' 260 characters (a valid name over ~165 made it exceed them under the real `%TEMP%`), two
   long names never share a stem, and the same name always gives the same one, so the `-2`, `-3` rule still
   prevents an overwrite. Rejected: plain truncation (two names alike in their first 80 characters would meet on
   the suffix rule only, and a reader could not tell them apart); `\\?\` long paths (every reader of the file
   would need them too).
6. **Limits fail, never truncate.** `max_entities` (200,000), `max_seconds` (3,600), `max_bytes` (100 MB,
   estimated while reading and checked on the final text) and `busy_patience` end the job as `failed` with the
   reason. A failed or cancelled job keeps **`<name>.failed.json`** (complete: false, state, reason, progress,
   counts so far), never a plain `.json`.
7. **One export at a time.** A second `export_drawing` while one runs answers the running `job_id`.
8. **What ActiveX does not expose is reported, never invented** ([schema](../concepts/export-schema.md)): a
   viewport's view centre and frozen layers, most dimension defining points and every dimension-line point, and
   the dimension's rendered text are `null` and listed in the entity's `unavailable`. The displayed text is
   computed from the dimension's own effective format properties, marked `displayed_text_source: "computed"`,
   and architectural, fractional, engineering, Windows units, DMS, arc symbols and tolerances are flagged
   `displayed_text_approximate`.
9. **Splines are exported exactly**: degree, control points, knots, weights when rational, fit points.

**Rejected:**
- Raising `TOOL_BUDGET` or paging `get_entities`: a supplier drawing with dimensions takes minutes over COM; no
  single call can, and paging would leave the agent to stitch spaces, blocks and counts together.
- Sharing the server's proxy with the thread: a COM object belongs to its apartment; calling it from another
  thread is undefined. A second `GetActiveObject` in the thread: with two AutoCADs registered, it may find the
  other one ([known gaps](../concepts/known-gaps.md) 3).
- Deleting a failed or cancelled export: the coordinator chose to keep `.failed.json` for diagnosis.
- Approximating splines as polylines: the control points are exact and smaller.
- **In-process routes, for now** (the coordinator's decision of 2026-11-01, after the speed measurement):
  - an ObjectDBX side database read from outside is still one cross-process call per property: no speed gain;
  - an AutoLISP `entget` reader would be ~100× faster and exact for the gaps of point 8 (DXF defpoints, the
    viewport's group 12 and 341 codes, the `*D` block's MText for the rendered text), but runs only on the active
    document with an idle command line, blocks AutoCAD's UI for its run, cannot be cancelled mid-run, needs a
    trusted path (`SECURELOAD`) and shows in the command history. **Phase 2 candidate, for dimensions and
    viewports only, decided after the live measurement**;
  - a .NET plugin is the fastest and most complete, but it is a plugin per AutoCAD release to build, sign and
    load, and this repo has none ("nothing runs inside AutoCAD").

## Consequences

- The tests pin it without AutoCAD: the schema on a fake drawing with one of everything, the displayed-text rule,
  the counts, the state machine, the limits, cancel, the naming, a busy AutoCAD, read-only, and the real pywin32
  calls (DISPID cache, marshalling) on Windows' `Scripting.Dictionary` ([test](../workflows/test.md)).
- **Live, 2026-11-01** (plain AutoCAD 2025, a real drawing of 68,798 entities, 3,152 dimensions;
  [live test](../workflows/live-test.md)): the marshalled proxy works against `acad.exe`; `export_drawing` answers
  in 5–11 ms; the job reads **685–795 entities/s** (~0.13–0.15 ms per COM call through the DISPID cache, no busy
  waits), so a whole drawing takes 1.5 minutes; other tools answer in 0.03 s meanwhile; cancel stops in 0.5 s; the
  drawing's layers and entities are unchanged. 0005's 10–65 ms per property was late binding on Civil 3D 2027
  with another tool in the session; the two were not compared on the same drawing.
- **Speed is not a reason for an in-process route**: exactness still is (point 8). The live run also fixed two
  things test-first: rotated dimensions have no extension-line points over ActiveX, and architectural text follows
  `SuppressZeroFeet` / `SuppressZeroInches`. The file is written as compact JSON.
- An export over 50 MB was pruned at the next server start; fixed the same day by the exports rule of point 5
  ([known gaps](../concepts/known-gaps.md) 16, closed). Rejected: only raising the 50 MB cap (one larger
  drawing breaks it again); a cap in bytes for `exports\` (the same, and it could still delete the newest).
  Root [0031](../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md) §4 states the
  folder-wide 7 days / 50 MB; this is a local exception for one artefact kind, recorded here and in 0003.
