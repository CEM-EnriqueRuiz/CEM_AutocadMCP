---
title: "CEM_AutocadMCP — overview"
type: overview
updated: 2026-10-24
sources: [README.md, autocad_mcp/server.py, pyproject.toml, setup_claude.ps1]
related: [index.md, concepts/upstream-and-fork.md, modules/server.md, concepts/com-connection.md]
tags: [overview]
---

# CEM_AutocadMCP overview

An MCP server that lets an AI agent such as Claude read and draw in a **running AutoCAD or Civil 3D** on the
same Windows machine. It is a fork of `thepiruthvirajan/autocad-mcp-server`
([upstream and fork](concepts/upstream-and-fork.md)).

```
Claude Desktop ──stdio (MCP)──> .venv\Scripts\python.exe -m autocad_mcp.server
                                   AutoCADCOMServer
                                     └─ COM (pywin32) ──> acad.exe (AutoCAD / Civil 3D), ActiveDocument
```

- **No plugin inside AutoCAD.** Unlike CEM_RevitMCP, CEM_NavisworksMCP or CEM_Civil3DMCP (which load an add-in
  and listen on a port), this server is an out-of-process COM client. Nothing is deployed into AutoCAD, and
  nothing to ACC or `ApplicationPlugins`.
- **One Python file does the work:** `autocad_mcp/server.py`, 21 tools to read the drawing, draw lines, circles,
  arcs, text, rectangles and simple building elements on predefined layers, recolour, and delete
  ([server](modules/server.md)).
- **It connects on the first tool call**, through every registered `AutoCAD.Application.*` ProgID
  ([0002](decisions/0002-lazy-connection-and-progid-discovery.md), [COM connection](concepts/com-connection.md)).
- **Reads change nothing; nothing is saved** ([0004](decisions/0004-reads-never-modify-the-drawing.md)), and every
  call ends inside the host's 60 s ([0005](decisions/0005-every-call-ends-inside-the-host-timeout.md)).
- **Files:** the server writes none; the user's scripts log to `%TEMP%\Cemengal\AutocadMCP\` through
  `autocad_mcp/temp_files.py` ([0003](decisions/0003-no-writes-under-acc-or-beside-scripts.md)).
- **Install:** `setup_claude.bat` builds `.venv` and registers the server with Claude Desktop
  ([connect an agent](workflows/connect-an-agent.md), [scripts](modules/scripts.md)).

## In the product family

One of the Autodesk MCP servers under `CEM_IA/`: CEM_RevitMCP (Revit), CEM_NavisworksMCP (Navisworks),
CEM_Civil3DMCP (Civil 3D, through a plugin on port 8080) and this one. Civil 3D is AutoCAD underneath, so this
server and CEM_Civil3DMCP can drive the same session at once ([COM connection](concepts/com-connection.md)).
It makes no CEM_API request. Python 3.10+ (the `.venv` runs 3.13), `mcp>=1.2,<2`, `pywin32`.
