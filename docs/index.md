---
title: "CEM_AutocadMCP wiki — index"
type: index
updated: 2026-11-05
sources: [README.md, autocad_mcp/server.py, CLAUDE.md]
related: [overview.md, log.md]
tags: [index]
---

# CEM_AutocadMCP wiki

## Start here

**1. Read [overview.md](overview.md).** CEM_AutocadMCP is a **fork of `thepiruthvirajan/autocad-mcp-server`**: a
Python MCP server over stdio (`autocad_mcp/server.py`) that drives a running AutoCAD or Civil 3D through COM
(`pywin32`). Claude Code (through `.mcp.json`) and Claude Desktop start it as
`.venv\Scripts\python.exe -m autocad_mcp.server`; nothing runs inside AutoCAD. Upstream vs our parts: [upstream and fork](concepts/upstream-and-fork.md).

**2. Hard rules.** Each links to its reason.

1. Change upstream code only for a recorded Cemengal need; mark it with a `# Cemengal` comment
   → [0001](decisions/0001-minimal-marked-divergence-from-upstream.md)
2. Every tool in `handle_list_tools` reaches a method through `handle_call_tool`, and no name is listed twice;
   `pytest` checks it → [server](modules/server.md)
3. Connect on the first tool call, never at the handshake; find AutoCAD through every `AutoCAD.Application.*`
   ProgID; never launch it unless `ACAD_AUTOSTART=1` → [0002](decisions/0002-lazy-connection-and-progid-discovery.md)
4. Nothing writes under ACC or beside its own script; logs and temporary artefacts go through `TempFolder` to
   `%TEMP%\Cemengal\AutocadMCP\`, which prunes itself and never through a junction or symlink → [0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md),
   root [0031](../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md)
5. A read never modifies the drawing; no tool saves one or creates one (with none open, say so); a structure
   creates only its own layer → [0004](decisions/0004-reads-never-modify-the-drawing.md)
6. Every tool call ends inside the host's 60 s: bound listings with `TOOL_BUDGET`, loop over handles not over
   model space, no `Regen` per entity → [0005](decisions/0005-every-call-ends-inside-the-host-timeout.md); a whole-drawing
   read runs as a background job on its own COM apartment, and a limit fails it, never truncates →
   [0006](decisions/0006-background-export-jobs.md)
7. In a session shared with another tool, never send `undo_last_operation` and check your own handles, not
   totals → [COM connection](concepts/com-connection.md)

**3. Before you change X, read Y.**

| Task / area | Read |
|---|---|
| Add or change a tool | [server](modules/server.md), [0005](decisions/0005-every-call-ends-inside-the-host-timeout.md), [test](workflows/test.md) |
| Connecting, ProgIDs, "Not connected to AutoCAD", a busy or slow AutoCAD | [COM connection](concepts/com-connection.md), [0002](decisions/0002-lazy-connection-and-progid-discovery.md), [scripts](modules/scripts.md) (`diag_com.py`) |
| Anything that writes a file (logs, screenshots, exports) | [0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md), [temp-files](modules/temp-files.md), root [0031](../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md) |
| `export_drawing`, its schema, the background jobs, dimension text | [export](modules/export.md), [export schema](concepts/export-schema.md), [0006](decisions/0006-background-export-jobs.md) |
| Layers, `create_structure`, anything that changes the drawing | [0004](decisions/0004-reads-never-modify-the-drawing.md), [server](modules/server.md) |
| Setup, the `.venv`, `.mcp.json`, Claude Desktop's config | [connect an agent](workflows/connect-an-agent.md), [scripts](modules/scripts.md) |
| Testing against a live AutoCAD | [live test](workflows/live-test.md) |
| Pulling from upstream | [upstream and fork](concepts/upstream-and-fork.md), [0001](decisions/0001-minimal-marked-divergence-from-upstream.md) |
| Anything | [known gaps](concepts/known-gaps.md): bulk deletes scan model space, `delete_entity_by_handle` is not bounded to it, undo is not ours, several tools not run live |

**4. Test and verify:** [test](workflows/test.md) with `.venv\Scripts\python.exe -m pytest -q`, then the
[live test](workflows/live-test.md) through MCP for anything COM-bound.

**5. Finish:** [finish a change](workflows/finish-a-change.md). Every commit carries its `docs/` update. Lint with
`python ../../tools/wiki/wiki_lint.py .`. The message is one line, `TYPE - Description. <issue URL>`, committed on
`main` after the user sends the issue link.

## Catalog

### Hub

- [overview.md](overview.md): what the server is, how Claude reaches AutoCAD, its place among the MCP servers.
- [log.md](log.md): append-only history of ingests, lints and queries.

### Modules

- [server](modules/server.md): `autocad_mcp/server.py`, `AutoCADCOMServer`, the 24 tools, the `ACAD_*` settings.
- [export](modules/export.md): `autocad_mcp/export.py` and `export_text.py`, the background export, `ComReader`, the jobs.
- [temp-files](modules/temp-files.md): `autocad_mcp/temp_files.py`, `TempFolder`, the self-cleaning temp folder.
- [scripts](modules/scripts.md): `setup_claude`, `diag_com`, `live_test`, upstream's `test_script.py`.

### Concepts

- [upstream-and-fork](concepts/upstream-and-fork.md): what upstream left unfinished, what the user and the fork changed, how to sync.
- [com-connection](concepts/com-connection.md): ProgIDs, the Running Object Table, a busy AutoCAD, slow calls, a shared session.
- [export-schema](concepts/export-schema.md): schema v1 of `export_drawing`'s JSON, the displayed-text rule.
- [known-gaps](concepts/known-gaps.md): what is missing, unverified or risky.

### Workflows

- [test](workflows/test.md): the pytest suite, the fake AutoCAD, what it cannot cover.
- [live-test](workflows/live-test.md): `live_test.py` through MCP stdio, with the recorded runs.
- [connect-an-agent](workflows/connect-an-agent.md): Claude Code through `.mcp.json`; Claude Desktop through the setup, and where its config lives.
- [finish-a-change](workflows/finish-a-change.md): commit with the wiki ingest.

### Decisions

- [0001](decisions/0001-minimal-marked-divergence-from-upstream.md): minimal, marked divergence from upstream (current).
- [0002](decisions/0002-lazy-connection-and-progid-discovery.md): connect lazily, through every registered ProgID; retry a busy AutoCAD, the pywin32 `AttributeError` race included (current).
- [0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md): no writes under ACC or beside the scripts; logs in a self-cleaning temp folder (current).
- [0004](decisions/0004-reads-never-modify-the-drawing.md): a read never modifies the drawing; no tool saves or creates one (current).
- [0005](decisions/0005-every-call-ends-inside-the-host-timeout.md): every tool call ends inside the host's 60 s (current).
- [0006](decisions/0006-background-export-jobs.md): a complete export runs as a background job, on COM, read only (current).

### Sources

- [commits 2025-07](sources/commits/2025-07.md): upstream's six commits.
- [commits 2026-10](sources/commits/2026-10.md): none without an issue; the record moved to #82.
- [commits 2026-11](sources/commits/2026-11.md): `autocad-mcp` declared in `.mcp.json`; the 2026-11-05 maintenance review (applied items, proposals P1–P9); the earlier record moved to CEM_Workspace#5.

### Issues

- [CEM-EnriqueRuiz/CEM_API#82](sources/issues/CEM-EnriqueRuiz-CEM_API-82.md): the fork's first commit: the user's rework, the onboarding, nothing written under ACC (0031), the live MCP runs, known gaps 12 and 13 fixed.
- [CEMENGAL/CEM_Workspace#5](sources/issues/CEMENGAL-CEM_Workspace-5.md): `export_drawing` (background, read only), the exports prune rule, the reparse-point guards (SEC-1), the review fixes (QA-1, QA-4, QA-6, QA-8, SEC-11).
