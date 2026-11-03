---
name: cem-autocadmcp-dev
description: Develop CEM_AutocadMCP, the AutoCAD MCP fork — the Python stdio MCP server that drives a running AutoCAD or Civil 3D through COM (pywin32), its tools, the ProgID discovery and lazy connection, the temp-folder log helper, the setup and diagnostic scripts, and the pytest suite. Triggers "AutoCAD MCP", "CEM_AutocadMCP", "autocad-mcp", "MCP tool for AutoCAD".
---

# CEM_AutocadMCP development

A fork of `thepiruthvirajan/autocad-mcp-server`. `autocad_mcp/server.py` is a Python MCP server over stdio
(`AutoCADCOMServer`, `mcp` low-level `Server`) that drives a running AutoCAD, or Civil 3D, through COM with
`pywin32`. Claude Code (through `.mcp.json`) and Claude Desktop start it as
`.venv\Scripts\python.exe -m autocad_mcp.server`; nothing runs inside AutoCAD. `setup_claude.ps1` builds the
`.venv` and registers the server with Claude Desktop; `diag_com.py` and `live_test.py` are
the user's diagnostic and live-test scripts.

**Before planning or editing, read [docs/index.md](../../../docs/index.md) ("Start here"), then the pages it names.**
Search with qmd when the index is not enough (`qmd query -c cem_autocadmcp "..."`).

## Hard rules

- It is a fork: change upstream code only for a recorded Cemengal need, and mark each change with a `# Cemengal`
  comment ([0001](../../../docs/decisions/0001-minimal-marked-divergence-from-upstream.md)).
- Every tool in `handle_list_tools` is dispatched by `handle_call_tool` to a method that exists, and no name is
  listed twice; `pytest` fails otherwise ([server](../../../docs/modules/server.md)).
- Connect lazily, on the first tool call: the MCP handshake never waits on AutoCAD, and AutoCAD is never launched
  unless `ACAD_AUTOSTART=1`. Find AutoCAD through every registered `AutoCAD.Application.*` ProgID, not only the
  generic one ([0002](../../../docs/decisions/0002-lazy-connection-and-progid-discovery.md)).
- Nothing writes under ACC (any path with an `ACCDocs` segment) or beside its own script. Logs and temporary
  artefacts go through `autocad_mcp.temp_files.TempFolder` to `%TEMP%\Cemengal\AutocadMCP\`, which prunes itself and never follows or deletes through a reparse point;
  `tests/test_no_acc_writes.py` guards it ([0003](../../../docs/decisions/0003-no-writes-under-acc-or-beside-scripts.md),
  root [0031](../../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md)).
- A read never modifies the drawing, and no tool saves or creates one: with no drawing open, answer
  `NO_DRAWING` so the agent asks the user. Structure layers are created only by the write that needs them
  ([0004](../../../docs/decisions/0004-reads-never-modify-the-drawing.md)).
- A busy AutoCAD is retried through `call_when_ready` / `safe_operation`, including pywin32's `AttributeError`
  race (`is_busy`); never treat an `AttributeError` from a COM object as "no such property" without it
  ([0002](../../../docs/decisions/0002-lazy-connection-and-progid-discovery.md)).
- Every tool call ends inside the host's 60 s. COM costs 10–65 ms per property and 1.7–3 s per `Regen` on a large
  drawing: bound listings with `TOOL_BUDGET` and say when they stop (`truncated`), loop over handles
  (`HandleToObject`) rather than model space, and redraw a new entity with `show()`, never a `Regen`
  ([0005](../../../docs/decisions/0005-every-call-ends-inside-the-host-timeout.md)).
- Test code never ships: the wheel packages only `autocad_mcp`; `tests/` stays outside it.
- In a shared AutoCAD session (another agent's Civil 3D plugin), never send `undo_last_operation`: AutoCAD's `U`
  undoes whatever ran last, not necessarily ours ([live test](../../../docs/workflows/live-test.md)).

## Verify

```powershell
.venv\Scripts\python.exe -m pytest -q          # unit and guard tests, no AutoCAD needed
.venv\Scripts\python.exe live_test.py          # live, through the MCP stdio server; needs a running AutoCAD
python ..\..\tools\wiki\wiki_lint.py .         # 0 errors
```

A live run is not coverage: pin what it showed with a unit test ([test](../../../docs/workflows/test.md)).

## Finish: commit-time ingest

Every commit carries its own wiki update (CROSS_REPO.md §4/§9): the source page in `docs/sources/` with each decision,
its reason and the rejected alternatives; the affected pages; `docs/index.md` for new pages; one `docs/log.md` entry.
Run `python ../../tools/wiki/wiki_lint.py .` to 0 errors and commit one line: `TYPE - Description. <issue URL>`
([finish a change](../../../docs/workflows/finish-a-change.md)).
