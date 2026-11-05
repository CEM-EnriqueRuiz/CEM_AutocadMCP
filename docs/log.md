---
title: "Wiki log"
type: log
updated: 2026-11-05
sources: []
related:
  - index.md
tags: [log]
---

# Wiki log

This log is append-only. Each entry uses the heading `## [YYYY-MM-DD] ingest|decision|lint|query | title`.

## [2026-10-24] ingest | Fork bootstrap: cem-autocadmcp-dev skill, wiki, pytest suite, the 0031 audit and the live MCP test

The coordinator forked `thepiruthvirajan/autocad-mcp-server` to `CEM-EnriqueRuiz/CEM_AutocadMCP` and renamed the
folder. Onboarded per the root's add-a-sibling-repo steps 2–4: schema files, the `cem-autocadmcp-dev` agent and
skill, this wiki, and a pytest suite (44 tests). Kept the user's uncommitted rework of 2026-10-17/18 as the
baseline ([0002](decisions/0002-lazy-connection-and-progid-discovery.md)). Fixed: the `.venv`'s editable install
after the rename; the scripts' logs beside themselves, now in `%TEMP%\Cemengal\AutocadMCP` through the new
`TempFolder` with a guard test ([0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md)); eleven layers
added to the drawing by a read ([0004](decisions/0004-reads-never-modify-the-drawing.md)); `get_drawing_info`
timing out on a 6,947-layer Civil 3D drawing, and a `Regen` per created entity
([0005](decisions/0005-every-call-ends-inside-the-host-timeout.md)); silent layer-tool failures; the setup missing
Claude's new config folder. Live through MCP on Civil 3D 2027: all checks passed, the drawing never saved
([live test](workflows/live-test.md)). Recorded in [sources/commits/2026-10](sources/commits/2026-10.md), with
upstream in [2025-07](sources/commits/2025-07.md); divergence in [upstream and fork](concepts/upstream-and-fork.md),
open items in [known gaps](concepts/known-gaps.md).

## [2026-10-24] ingest | Live MCP run on plain AutoCAD 2027

The coordinator gave the AutoCAD slot with Civil 3D closed. Plain AutoCAD 2027 (`/product ACAD`, as its shortcut)
opened the X-C3D test drawing read-only, Civil objects as proxies; no security prompt, since
`CEM_Civil3DMCP.bundle` is `Platform="Civil3D"`. `live_test.py` through MCP stdio passed every check, the budget
held at 40 s, and AutoCAD quit without saving; the ACC watcher recorded nothing in the window. Recorded in the
[live test](workflows/live-test.md) with what differs from Civil 3D, in [COM connection](concepts/com-connection.md),
as [known gaps](concepts/known-gaps.md) 12 (a busy AutoCAD surfaces as an unretried `AttributeError`) and 13 (a
blank drawing added on the Start tab), with item 3 rewritten, and in [sources/commits/2026-10](sources/commits/2026-10.md).

## [2026-10-24] ingest | Known gaps 12 and 13 closed: the pywin32 busy race is retried, no tool creates a drawing

At the coordinator's request, both gaps from the plain AutoCAD run were fixed test-first with the fake COM objects.
`is_busy` recognises pywin32's `AttributeError` for a refused name lookup by asking the same object for the same
name again, and `call_when_ready` retries it within the busy budget, in `safe_operation` and the connection's
reads; a real missing property is not retried ([0002](decisions/0002-lazy-connection-and-progid-discovery.md)).
With no drawing open, every tool answers "No drawing is open in AutoCAD…" instead of adding one
([0004](decisions/0004-reads-never-modify-the-drawing.md), retitled). 13 new tests, 57 in all. Updated
[known gaps](concepts/known-gaps.md) (12 and 13 closed), [COM connection](concepts/com-connection.md),
[server](modules/server.md), [test](workflows/test.md), [live test](workflows/live-test.md),
[upstream and fork](concepts/upstream-and-fork.md), the index's hard rule 5, the dev skill's hard rules, and
[sources/commits/2026-10](sources/commits/2026-10.md).

## [2026-10-25] ingest | CEM-EnriqueRuiz/CEM_API#82 the fork's first commit: nothing under ACC, onboarding, live MCP runs

The user tested pass 1 and sent the issue link: keep every change and commit it, with the user's own earlier rework
that it built on. The pass-1 record moved from `sources/commits/2026-10` to
[sources/issues/CEM-EnriqueRuiz-CEM_API-82](sources/issues/CEM-EnriqueRuiz-CEM_API-82.md), with the user's
decisions of 2026-10-25, the files in the commit and those left out, the tests (57) and the watcher result. Root
0031 now holds the MCPs to the rule with no exception, noted in [0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md).
[Known gaps](concepts/known-gaps.md) 8: the tracked upstream bytecode stays for a change of its own.
[Test](workflows/test.md) names the root runner's `autocadmcp` target. Index: the issue page.

## [2026-11-01] ingest | export_drawing: a complete read-only export of a drawing, run in the background

From the architect's brief (the user wants the MCP to read what Codex read through PowerShell COM). After the
coordinator approved the plan, three tools were built test-first on the fake COM objects: `export_drawing`,
`get_export_status`, `cancel_export`. The job runs on its own thread and COM apartment with a marshalled proxy, reads
through a DISPID cache, walks model space, every layout with its viewports and the referenced block definitions,
and writes one JSON (schema v1) under `%TEMP%\Cemengal\AutocadMCP\exports\`, never overwriting. Limits fail the job
with the reason and keep a `.failed.json`. Dimensions carry measurement, override and a computed displayed text;
what ActiveX lacks is listed as `unavailable`. 140 tests (57 before). Not run live: AutoCAD was not running.
New: [0006](decisions/0006-background-export-jobs.md), [export](modules/export.md),
[export schema](concepts/export-schema.md), [sources/commits/2026-11](sources/commits/2026-11.md). Updated:
[server](modules/server.md), [overview](overview.md), [known gaps](concepts/known-gaps.md) 14 and 15,
[test](workflows/test.md), [temp-files](modules/temp-files.md), [live test](workflows/live-test.md),
[COM connection](concepts/com-connection.md), [0005](decisions/0005-every-call-ends-inside-the-host-timeout.md), the index.

## [2026-11-01] ingest | export_drawing live on AutoCAD 2025: 685–795 entities/s, two fixes

On the coordinator's go, a scratch MCP client ran the export twice against a real drawing the user had open
(68,798 entities; names and contents kept out of the wiki). Read only, `done` in 100 s, cancel in 0.5 s, other tools
answering in 0.03 s meanwhile. Fixed test-first: rotated dimensions lack extension-line points in AutoCAD 2025, and
architectural text follows the zero-feet / zero-inches suppression; compact JSON. Run 2: 795 entities/s. 147 tests.
Updated [live test](workflows/live-test.md), [0006](decisions/0006-background-export-jobs.md),
[export schema](concepts/export-schema.md), [known gaps](concepts/known-gaps.md) 14–16,
[COM connection](concepts/com-connection.md), [test](workflows/test.md),
[sources/commits/2026-11](sources/commits/2026-11.md).

## [2026-11-01] ingest | Known gap 16 closed: exports\ keeps the last 3, never the newest, outside the 50 MB cap

The architect asked that an export survive the prune at the next server start. Test-first in `TempFolder`
(`prune_exports`, also run after each job) and in `setup_claude.ps1`'s twin: the newest export and the newest
complete one at any age, the others up to 3 files and 7 days; the rest of the folder keeps 7 days / 50 MB. The
tool description states it. 154 tests. Updated [temp-files](modules/temp-files.md),
[0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md) (amended), [0006](decisions/0006-background-export-jobs.md),
[known gaps](concepts/known-gaps.md) 16, [export](modules/export.md), [test](workflows/test.md),
[sources/commits/2026-11](sources/commits/2026-11.md).

## [2026-11-01] ingest | Review fix batch: the prune follows no reparse point (SEC-1), QA-1, QA-4, QA-6

Test-first. Both prunes (`TempFolder`, `setup_claude.ps1`) never enter or delete through a junction or symlink,
at the root, its parent, `exports\`, a subfolder or a file, and re-check before each delete; the Python exports rule
agrees with the PowerShell one on an old second complete export; the COM stream is marshalled only when a job is
accepted and released otherwise; hostile drawing names are pinned. 183 passed, 1 skipped. Updated
[0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md) (point 6), [0006](decisions/0006-background-export-jobs.md),
[temp-files](modules/temp-files.md) (the check), [export](modules/export.md), [test](workflows/test.md),
[known gaps](concepts/known-gaps.md) 17, the index's rule 4, the dev skill, [sources/commits/2026-11](sources/commits/2026-11.md).

## [2026-11-01] ingest | Known gap 17 narrowed: no write goes through a junctioned temp folder

Test-first: `TempFolder._prepare` refuses a junctioned `Cemengal`, root or artefact folder, before the prune and
after `mkdir`; `export_drawing` answers the reason instead of writing. 187 passed, 1 skipped. Updated
[0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md) point 6, [temp-files](modules/temp-files.md),
[known gaps](concepts/known-gaps.md) 17 (the race only), [test](workflows/test.md),
[sources/commits/2026-11](sources/commits/2026-11.md).

## [2026-11-01] ingest | setup_claude.ps1 refuses to write its transcript through a junction

Test-first: `Assert-CemWritableTemp`, the PowerShell twin of `_prepare`'s refusal, runs before the prune and after
the folder is made, before `Start-Transcript`. 193 passed, 1 skipped. Updated
[0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md) point 6, [temp-files](modules/temp-files.md),
[known gaps](concepts/known-gaps.md) 17, [test](workflows/test.md), [sources/commits/2026-11](sources/commits/2026-11.md).

## [2026-11-01] ingest | QA-8: a long drawing name gets a bounded, hashed stem

Test-first: `safe_stem` keeps a 71-character prefix plus `~` and 8 hex of a SHA-1 when the stem exceeds 80
characters, so a 300-character name exports under Windows' 260-character path and two long names never collide;
the never-overwrite rule is unchanged. 196 passed, 1 skipped. Updated [0006](decisions/0006-background-export-jobs.md),
[export](modules/export.md), [test](workflows/test.md), [sources/commits/2026-11](sources/commits/2026-11.md).

## [2026-11-01] ingest | CEMENGAL/CEM_Workspace#5: export_drawing, the exports prune rule, the reparse-point guards

The user chose one umbrella issue for the 2026-11-01 MCP modeller work. The record moved from
`sources/commits/2026-11` to [sources/issues/CEMENGAL-CEM_Workspace-5](sources/issues/CEMENGAL-CEM_Workspace-5.md),
with an end-state table of every finding (SEC-1 High, QA-1, QA-4, QA-6/SEC-6, QA-8, SEC-11, known gaps 16 and 17):
0 open blocking findings, 196 passed and 1 skipped. Index: the issue page;
[0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md) and [0006](decisions/0006-background-export-jobs.md)
cite the issue. Committed as one commit, not pushed.

## [2026-11-04] ingest | autocad-mcp declared in .mcp.json

The user asked for each repo's `.mcp.json` to declare the servers its development needs, committed with no issue
link and with reviews skipped. `.mcp.json` gained a relative `autocad-mcp` entry, and the tracked
`.claude/settings.local.json` enables it. Recorded in [sources/commits/2026-11](sources/commits/2026-11.md), with the
rejected alternatives. Corrected what said only Claude Desktop starts the server:
[connect an agent](workflows/connect-an-agent.md), [scripts](modules/scripts.md), [server](modules/server.md),
[overview](overview.md), [index](index.md), `CLAUDE.md` and the skill. Not pushed.

## [2026-11-05] ingest | Overnight maintenance review

The overnight maintenance review (run `run_00597272b2d2`) left five items uncommitted; the user said on 2026-11-05 to
commit them with no issue link and without the QA and security reviews. Applied: the two invalid-escape
`SyntaxWarning`s in the tests fixed (A1); four unused names removed, `APPROXIMATE_UNITS` among them (A2); upstream's
tracked `cpython-312` bytecode deleted, closing [known gap](concepts/known-gaps.md) 8 (A3); the three old dev logs
moved out of the repo and their `.gitignore` lines dropped, closing gap 11 (A4); wiki drift fixed, with
`delete_entity_by_handle`'s missing model-space bound recorded as gap 18 (A5). 196 passed, 1 skipped, 0 warnings.
Recorded in [sources/commits/2026-11](sources/commits/2026-11.md) with the decisions and the proposals not applied
(P1–P9); [upstream and fork](concepts/upstream-and-fork.md) notes the bytecode's deletion. Not pushed.
