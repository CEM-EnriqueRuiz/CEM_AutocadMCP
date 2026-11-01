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

**`export_drawing`** is not in `live_test.py`; it was run live with a scratch client (below). Its live test: the user
opens a drawing with real dimensions in AutoCAD and gives its exact path (no supplier drawing otherwise, never a
walk of `C:\DC`); start the export, follow `get_export_status` to `done`, record entities per second, the
`unavailable` and `errors` a real drawing shows and the `Saved` flag before and after; cancel a second run. Read
only: the drawing stays as it was. Record counts and timings only, never the drawing's names or contents.

## Recorded runs

**2026-11-01, plain AutoCAD 2025** (`Version` 25.1, ProgID `AutoCAD.Application`), alone on the machine, a real
supplier drawing the user opened and the coordinator named by exact path (its name and contents stay out of this
wiki; the JSON stayed in `%TEMP%`). 56 layers; 47,586 entities in model space, 14 paper-space layouts with 53
viewports, 226 block definitions: 68,798 entities in all. The drawing's `Saved` flag was already false (the user's
session). A scratch MCP client started this repo's `.venv` server over stdio from `%TEMP%`, as Claude Desktop does.
- Run 1, 11:59: `export_drawing` answered in 5 ms; the job ended `done` in 100 s, **685 entities/s**, 658,035 COM
  calls (~0.15 ms each), 0 busy waits; `get_drawing_info` called meanwhile answered in 0.03 s each time. 67,430
  read, 1,368 skipped with their reason (hatches 966, 2D solids 376, OLE 15, RText 5, wipeouts 4, PDF underlays
  2), 0 failed; 3,152 dimensions, 2,945 in architectural units. A second export, cancelled after 8 s, stopped in
  0.5 s as `cancelled` with its `.failed.json` and no plain `.json`. Layers and entities unchanged after.
- What it showed, fixed the same hour test-first: AutoCAD 2025's `IAcadDimRotated` has no `ExtLine1Point` /
  `ExtLine2Point` (type info; all 2,987 rotated dimensions), and architectural text must follow `SuppressZeroFeet`
  / `SuppressZeroInches` (1,541 dimensions under a foot, 407 whole feet). Also: 22 dimensions refuse
  `Measurement` with "object not open for write" and one 2D polyline refuses `GetBulge` ("invalid input"); both
  are recorded in the entities' `errors`, nothing retried.
- Run 2, 12:03, after the fixes: `done` in 87.5 s, **795 entities/s**, same counts; the computed architectural texts
  take AutoCAD's shapes (`6'-6 1/2"`, `6 1/2"`, `6'-0"`); cancel again in 0.5 s. The file is 50.0 MB with compact
  JSON (run 1, indented separators: 53.7 MB). **Run 1's file was gone**: the temp folder's prune at run 2's server
  start deleted it, being over 50 MB ([known gaps](../concepts/known-gaps.md) 16).

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
