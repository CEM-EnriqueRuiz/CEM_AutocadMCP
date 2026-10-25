---
title: "Connect an agent — register the server with Claude Desktop"
type: workflow
updated: 2026-10-24
sources: [setup_claude.ps1, README.md, live_test.py]
related: [../modules/scripts.md, live-test.md, ../decisions/0002-lazy-connection-and-progid-discovery.md]
tags: [claude, setup]
---

# Connect an agent

1. Clone the repo to a **local disk** (not under `C:\DC\ACCDocs`: the setup refuses it).
2. Double-click `setup_claude.bat`. It builds `.venv`, installs the package editable, checks COM, and adds
   this to Claude Desktop's config, keeping a `.bak-autocad` copy:

   ```json
   "autocad-mcp": {
     "command": "D:\\repos\\Cemengal\\CEM_IA\\CEM_AutocadMCP\\.venv\\Scripts\\python.exe",
     "args": ["-m", "autocad_mcp.server"]
   }
   ```
3. Quit Claude Desktop from the tray and reopen it. Open AutoCAD or Civil 3D with a drawing; the server connects
   on the first tool call, not at startup.

**Where the config is.** The Store (MSIX) app keeps it in `%LOCALAPPDATA%\Claude-Data\claude_<id>\` since
2026-10-20; older installs use `%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\` or
`%APPDATA%\Claude\`. The setup writes to every one that exists.

**After moving the repo folder** run `.venv\Scripts\python.exe -m pip install -e .` and point the config's
`command` at the new path. Check it from another folder, as Claude starts it:
`cd C:\ ; <repo>\.venv\Scripts\python.exe -c "import autocad_mcp"`.

Optional `env` block: `ACAD_PROGID`, `ACAD_AUTOSTART`, `ACAD_OP_DELAY`, `ACAD_TOOL_BUDGET`
([server](../modules/server.md)).
