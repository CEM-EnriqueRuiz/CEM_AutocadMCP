---
title: "Wiki log"
type: log
updated: 2026-10-25
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
