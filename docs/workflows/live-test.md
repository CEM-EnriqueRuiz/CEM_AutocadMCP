---
title: "Live test — through the MCP stdio server against a running AutoCAD or Civil 3D"
type: workflow
updated: 2026-10-24
sources: [live_test.py, live_test.bat, "the live runs of 2026-10-24"]
related: [test.md, connect-an-agent.md, ../concepts/com-connection.md, ../decisions/0004-reads-never-modify-the-drawing.md, ../decisions/0005-every-call-ends-inside-the-host-timeout.md]
tags: [live, mcp, smoke-test]
---

# Live test

```powershell
.venv\Scripts\python.exe live_test.py      # or double-click live_test.bat
```

`live_test.py` is an MCP client (`mcp.ClientSession` over `stdio_client`). It starts the server exactly as Claude
Desktop does, from the `autocad-mcp` entry of Claude's config (read only), with the working folder set to
`%TEMP%` so a broken install path shows up. Then, against the active drawing:

1. reads the layer count straight through COM (read only), then `get_drawing_info`: the counts must match,
   so the read added no layer;
2. `get_entities(max_entities=25)`;
3. `create_line` (thick, four entities), `create_circle`, `create_arc`, `create_text` on the current layer,
   then `change_entity_color` on the circle;
4. `delete_entity_by_handle` on the text, `delete_entities_by_handles` on the rest, then again on all of them:
   every handle must come back in `not_found`;
5. `get_drawing_info`: the layer names must be unchanged.

It exits 1 on any failed check and logs to `%TEMP%\Cemengal\AutocadMCP\live-test-yyyyMMdd.log`.

**Never in a live test on a real drawing:** saving; `delete_entities_by_layer`, `_by_type`, `_by_color`,
`_by_type_and_color`, `delete_last_entities`, `delete_all_entities` (they hit the user's entities);
`undo_last_operation` (it undoes whatever ran last, possibly another tool's work); `create_structure` and the
layer tools (they add layers, which no tool removes); `zoom_extents` (it moves the user's view). Creating and
deleting entities leaves the drawing's `Saved` flag false: close without saving.

## Recorded runs

**2026-10-24, Civil 3D 2027** (`acad.exe` pid 3016, ProgID 26), `CEM_Test\MCP\X-C3D-CSLZ-25012720_SERVICE
PROP_CORR.dwg`: 6,947 layers, 958 entities, with the CEM_Civil3DMCP agent working in the same session.
- Run 1, 21:01: the server started from `%TEMP%` (after `pip install -e .` fixed the `.venv`), `initialize` and
  `list_tools` (21 tools) answered, then `get_drawing_info` timed out at 60 s: listing every layer takes ~5 min.
  Led to [0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md).
- Run 2, 21:05, after 0005: **all checks passed** in 17 s. `get_drawing_info` 4.0 s (6,947 layers before and
  after); `get_entities` 2.0 s; `create_line` thick 0.54 s (handles 256DA–256DD); circle, arc, text ~0.1 s each;
  `change_entity_color` 0.03 s; `delete_entity_by_handle` 1.45 s; `delete_entities_by_handles` 0.15 s, then
  0 deleted and 7 not found; 958 entities and the current layer `_TRAVAIL` as before; `Saved` true before the
  creates, false after.
- Budget check, 21:06, read only: `get_entities` (all) stopped at 40.1 s with 745 of 958 and `truncated: true`;
  `get_drawing_info(max_layers=10000)` stopped at 40.1 s with 977 layers and `layers_truncated: true`.
- The ACC file watcher recorded no event naming AutoCAD, a drawing or `AutocadMCP`, and none during these runs.

**2026-10-24, plain AutoCAD 2027**, alone on the machine (Civil 3D closed): `acad.exe /product ACAD /language
"es-ES"` from `…\AutoCAD 2027\UserDataCache\`, as the installed shortcut does (pid 7580, 21:34:11–21:40:07). The
same drawing opened read-only through COM (`Documents.Open(path, True)`); the Civil objects are proxies.
- No security prompt: `CEM_Civil3DMCP.bundle` declares `Platform="Civil3D"`, so plain AutoCAD does not load it.
  The windows seen were the main frame, the Start tab, `Dibujo1.dwg`, two toolbars and the External References
  palette (the drawing's xrefs are not found); no modal dialog.
- Run 3, 21:37:54–21:38:13: **all checks passed**, 19 s. `get_drawing_info` 5.0 s (6,947 layers before and after,
  `application: "AutoCAD"`); `get_entities` 2.0 s; `create_line` thick 0.53 s (256EE–256F1); circle, arc, text
  0.12–0.14 s; `change_entity_color` 0.04 s; `delete_entity_by_handle` 1.37 s; `delete_entities_by_handles` 0.17 s,
  then 0 deleted and 7 not found; 958 entities and `_TRAVAIL` as before.
- Budget check, 21:38–21:39, read only: `get_entities` (all) stopped at 40.1 s with 590 of 958; `get_drawing_info
  (max_layers=10000)` at 40.0 s with 752 layers. Proxies read about a fifth slower than Civil 3D's native objects.
- Closed with `Close(False)` and `Quit()`; AutoCAD exited without a prompt. The DWG kept its 2026-10-20 18:16:48
  time stamp; no `.bak` or `.dwl`. The watcher recorded no event at all from 21:33:58 to 21:40:30.

What differs from Civil 3D's `acad.exe`:
- `Application.Name` is `AutoCAD`, not `Autodesk Civil 3D 2027`; the version and ProgID (`26`) are the same.
- `ObjectName` still gives the Civil class (`AeccDbPipe`, `AeccDbStructure`, …) for the proxies; the server
  reads them as plain entities, and the counts match Civil 3D's.
- **`Saved` is already false right after the read-only open**, before any tool call: AutoCAD itself marks this
  drawing modified when it opens it (proxies, unresolved xrefs). In Civil 3D it stayed true until the creates.
- **Startup race:** right after launch, and while `Documents.Open` was busy, `GetActiveObject` succeeded but
  reading `.Name` raised `AttributeError`. Fixed the same day: the server retries that race like any busy call
  ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md); [known gaps](../concepts/known-gaps.md) item 12, closed).
- On the Start tab AutoCAD has no document (`Documents.Count == 0`); the server's first call added a blank
  drawing. Fixed the same day: every tool now answers "No drawing is open in AutoCAD…"
  ([0004](../decisions/0004-reads-never-modify-the-drawing.md); item 13, closed). Neither fix was run live yet
  (the AutoCAD slot had moved on); both are pinned with fakes.
