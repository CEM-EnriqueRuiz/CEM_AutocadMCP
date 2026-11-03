# CEM_AutocadMCP

A fork of `thepiruthvirajan/autocad-mcp-server`: a Python MCP server over stdio (`autocad_mcp/server.py`,
`AutoCADCOMServer`) that drives a running AutoCAD, or Civil 3D, through COM (`pywin32`). Claude Code (through `.mcp.json`)
and Claude Desktop start it as `.venv\Scripts\python.exe -m autocad_mcp.server`; there is no plugin inside AutoCAD.

**Read [docs/index.md](docs/index.md) ("Start here") before planning or editing**, then the pages it
names. The wiki holds the conventions, the decisions and their reasons, and the known gaps. The
upstream README describes upstream's intent; the code and the wiki win.

Load the `cem-autocadmcp-dev` skill (`.claude/skills/cem-autocadmcp-dev/SKILL.md`) before writing code.
Cross-repo rules: [../../CROSS_REPO.md](../../CROSS_REPO.md).

Every commit carries its wiki update ([docs/workflows/finish-a-change.md](docs/workflows/finish-a-change.md)).
Commit message: `FEAT|FIX|REFACTOR|DOCS - Description. <issue URL>`. **That line is the entire
message**: no body, no file list, no test tally, no `Co-Authored-By`. Use one `git commit -m "..."`.
