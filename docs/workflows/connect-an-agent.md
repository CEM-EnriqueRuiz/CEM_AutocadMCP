---
title: "Connect an agent — Claude Code through .mcp.json, Claude Desktop through the setup"
type: workflow
updated: 2026-11-04
sources: [.mcp.json, .claude/settings.local.json, setup_claude.ps1, README.md, live_test.py]
related: [../modules/scripts.md, live-test.md, ../decisions/0002-lazy-connection-and-progid-discovery.md, ../sources/commits/2026-11.md]
tags: [claude, setup]
---

# Connect an agent

## Claude Code, inside this repo

The tracked `.mcp.json` declares the server, and the tracked `.claude/settings.local.json` enables it. There is
nothing to register:

```json
"autocad-mcp": { "type": "stdio", "command": ".venv/Scripts/python.exe", "args": ["-m", "autocad_mcp.server"] }
```

The path is relative because Claude Code starts a project server with the project as its working directory, so the
entry works from any checkout ([why](../sources/commits/2026-11.md)). The `.venv` is not tracked: a fresh checkout
must build it first, and until then this server does not start. `setup_claude.bat` builds it, and also registers
the server with Claude Desktop (below).

## Claude Desktop

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
`command` at the new path. Check it from another folder, as Claude Desktop starts it:
`cd C:\ ; <repo>\.venv\Scripts\python.exe -c "import autocad_mcp"`.

Optional `env` block: `ACAD_PROGID`, `ACAD_AUTOSTART`, `ACAD_OP_DELAY`, `ACAD_TOOL_BUDGET`
([server](../modules/server.md)).
