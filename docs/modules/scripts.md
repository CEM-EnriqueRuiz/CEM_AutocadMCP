---
title: "scripts — setup_claude, diag_com, live_test, test_script"
type: module
updated: 2026-10-24
sources: [setup_claude.ps1, setup_claude.bat, diag_com.py, diag_com.bat, live_test.py, live_test.bat, test_script.py]
related: [../workflows/connect-an-agent.md, ../workflows/live-test.md, ../decisions/0003-no-writes-under-acc-or-beside-scripts.md, temp-files.md]
tags: [module, scripts, setup]
---

# scripts

The user wrote the first three on 2026-10-17/18, before the fork; each `.bat` runs its script by double-click
and ends with `pause`.

| Script | What it does | Writes |
|---|---|---|
| `setup_claude.bat` → `setup_claude.ps1` | refuses an ACC folder; finds Python ≥ 3.10; creates `.venv`; `pip install -e .`; checks COM against a running AutoCAD; adds `autocad-mcp` to every Claude Desktop config it finds (`Get-ClaudeConfigs`: the Store app's `%LOCALAPPDATA%\Claude-Data\claude_<id>` since 2026-10-20, its older `Packages\Claude*\LocalCache\Roaming\Claude`, the classic `%APPDATA%\Claude`), keeping a `.bak-autocad` copy | transcript `%TEMP%\Cemengal\AutocadMCP\setup-yyyyMMdd.log`; `.venv`; Claude's config |
| `diag_com.bat` → `diag_com.py` | why `GetActiveObject` fails: the generic ProgID's CLSID and `CurVer`, every `AutoCAD.Application.*` ProgID, the Running Object Table, each `GetActiveObject`, the `acad.exe` processes | `%TEMP%\Cemengal\AutocadMCP\diag-yyyyMMdd.log` |
| `live_test.bat` → `live_test.py` | the live test through MCP stdio ([live test](../workflows/live-test.md)) | `%TEMP%\Cemengal\AutocadMCP\live-test-yyyyMMdd.log` |
| `test_script.py` | upstream's COM smoke test: draws lines, a circle, text, polylines and an arc in the active drawing, and leaves them | nothing on disk; **modifies the drawing** |

Each log run appends a `=== yyyy-mm-dd hh:mm:ss` block, and the script prints the log's path.

- Never run `test_script.py` on a real drawing: it adds entities and does not delete them. It is not the MCP
  server and not a test in `tests/`.
- After the folder was renamed from `autocad-mcp-server` (2026-10-24), the `.venv`'s editable install still
  pointed at the old path, so `python -m autocad_mcp.server` failed from any other folder, as Claude Desktop
  starts it. `.venv\Scripts\python.exe -m pip install -e .` rewrites the `.pth`; do it after any move. The
  `.venv`'s `pip.exe` and the other launchers still embed the old path: call `python -m pip`.
- Until 2026-10-24 the setup looked only in the classic and `Packages` folders. After the Store app moved its
  data to `Claude-Data` (2026-10-20), a re-run would have written a new config in `%APPDATA%\Claude` that Claude
  never reads. `tests/test_setup_prune.py` pins the three locations.
