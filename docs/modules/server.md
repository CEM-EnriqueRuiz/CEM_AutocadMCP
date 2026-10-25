---
title: "server — autocad_mcp/server.py, the MCP server"
type: module
updated: 2026-10-24
sources: [autocad_mcp/server.py, pyproject.toml, tests/test_tool_contract.py]
related: [../concepts/com-connection.md, ../decisions/0002-lazy-connection-and-progid-discovery.md, ../decisions/0004-reads-never-modify-the-drawing.md, ../decisions/0005-every-call-ends-inside-the-host-timeout.md, temp-files.md]
tags: [module, mcp, com]
---

# server: `autocad_mcp/server.py`

One class, `AutoCADCOMServer`, wraps both the MCP low-level `Server` (`self.server`, name `autocad-com-mcp`) and
the COM connection (`self.acad_app`, `self.doc`). `main()` registers the tools and serves stdio; `run()` is the
console entry point (`autocad-com-mcp` in `pyproject.toml`). Claude Desktop runs `python -m autocad_mcp.server`.

## Shape of a tool

A tool lives in three places that must agree; `tests/test_tool_contract.py` checks it:
1. a `types.Tool(name=…, inputSchema=…)` in `handle_list_tools`;
2. an `elif name == "…"` branch in `handle_call_tool` that reads `arguments` and calls the method;
3. the method on `AutoCADCOMServer`, which starts with `if not self.ensure_connection(): return self.not_connected()`
   and returns a JSON-able `dict` (`{"success": True, …}` or `{"error": "…"}`). With no drawing open,
   `not_connected()` answers `NO_DRAWING` ("No drawing is open in AutoCAD…"); nothing creates a drawing
   ([0004](../decisions/0004-reads-never-modify-the-drawing.md)).

Inside a method, COM calls that may meet a busy AutoCAD go through `safe_operation` (returns `None` and sets
`last_error`) or `call_when_ready` (raises); both retry what `is_busy` accepts
([0002](../decisions/0002-lazy-connection-and-progid-discovery.md)).

The handler serialises the dict as one `TextContent`. Unknown names are refused by `mcp` itself (the tool is not
listed) before the handler's own `Unknown tool` branch.

## Tools (21)

| Group | Tools | Notes |
|---|---|---|
| Read | `get_drawing_info(max_layers=100)`, `get_entities(max_entities?)` | bounded by the 40 s budget; `layers_truncated` / `truncated` ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md)) |
| Create | `create_line`, `create_circle`, `create_rectangle`, `create_text`, `create_arc`, `create_structure` | `thickness > 0` draws parallels and caps; `show()` redraws each entity, no `Regen` |
| Layers | `create_or_get_layer`, `set_current_layer` | on failure they say why (not connected, or the layer) |
| Edit | `change_entity_color`, `zoom_extents`, `undo_last_operation` | undo sends AutoCAD's `U` with `SendCommand`: it undoes whatever ran last |
| Delete | `delete_entity_by_handle`, `delete_entities_by_handles` | by `HandleToObject`, model space only |
| Bulk delete | `delete_entities_by_type`, `_by_layer`, `_by_color`, `_by_type_and_color`, `delete_last_entities`, `delete_all_entities(confirm)` | scan model space (`_snapshot_entities`, `_delete_where`); slow on large drawings |

`create_structure` maps a type to a predefined layer (`get_layer_for_structure_type`: wall → `WALLS`,
door → `DOORS`, …), creates that one layer if missing (`ensure_structure_layer`), switches to it, draws, labels
on `ANNOTATION`, and restores the current layer ([0004](../decisions/0004-reads-never-modify-the-drawing.md)).

## Settings (environment)

| Variable | Default | Effect |
|---|---|---|
| `ACAD_PROGID` | — | force one ProgID, e.g. `AutoCAD.Application.26` |
| `ACAD_AUTOSTART` | `0` | `1` launches AutoCAD when none runs (it opens no drawing) |
| `ACAD_OP_DELAY` | `0.05` | pause after each COM operation, in seconds |
| `ACAD_TOOL_BUDGET` | `40` | seconds a listing may run ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md)) |

## Gotchas

- `win32com.client.constants` is empty unless makepy generated the type library, so AutoCAD enums are literals
  (`ACAD_REGEN_ALL = 1`).
- Late binding turns a refused name lookup into `AttributeError('<object>.<name>')`; never catch
  `AttributeError` as "no such property" around a COM call without `is_busy`.
- Points are `VARIANT(VT_ARRAY | VT_R8, [x, y, z])` (`create_variant_point`); plain tuples fail.
- The server writes no file. Do not add logging to a file here without `TempFolder`
  ([0003](../decisions/0003-no-writes-under-acc-or-beside-scripts.md)); stdout is the MCP channel, so never `print`.
