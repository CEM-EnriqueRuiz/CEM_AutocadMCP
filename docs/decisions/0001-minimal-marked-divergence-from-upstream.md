---
title: "0001 — Diverge from upstream minimally, and mark every change"
type: decision
status: current
updated: 2026-10-24
sources: [../../CROSS_REPO.md, autocad_mcp/server.py, LICENSE]
related: [../concepts/upstream-and-fork.md, ../sources/commits/2025-07.md, ../sources/issues/CEM-EnriqueRuiz-CEM_API-82.md]
tags: [fork, upstream]
---

# 0001 — Diverge from upstream minimally, and mark every change

## Context

[CROSS_REPO §5](../../../../CROSS_REPO.md) treats forks as not Cemengal-original: CEM_RevitMCP and
CEM_NavisworksMCP keep upstream's architecture and mark what they changed. This upstream,
`thepiruthvirajan/autocad-mcp-server`, is six commits from July 2025 by one author, quiet since, so a sync is
unlikely. It was also unfinished: nine advertised tools had no method (see [upstream and fork](../concepts/upstream-and-fork.md)).

## Decision

- Change upstream code only for a recorded Cemengal need or a bug that breaks a tool.
- Mark each change in an upstream file with a `# Cemengal` comment saying what changed and why, linking the
  decision where there is one. `git grep -n "Cemengal" -- autocad_mcp pyproject.toml` lists the divergence.
- Cemengal-only files need no marking: `docs/`, `tests/`, `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.agents/`,
  `.mcp.json`, `.gitattributes`, `autocad_mcp/temp_files.py`, and the user's scripts (`setup_claude.*`,
  `diag_com.*`, `live_test.*`).
- Keep upstream's `LICENSE` (Apache-2.0) and its README; the README's Claude Desktop section is ours.
- Do not restyle upstream code (bare `except:`, long methods) unless a change needs it.

**Exception, recorded here.** The user's own pre-fork rework of `server.py` (2026-10-17/18: ProgID discovery,
COM busy retries, the nine missing tools, the `Regen` constant) predates this rule and carries no
`Cemengal` comments. It is listed in [upstream and fork](../concepts/upstream-and-fork.md) instead of being
re-annotated line by line.

**Rejected:** rewriting the server as a class per tool, or onto FastMCP. It is a working tool with one file;
a rewrite would make every line ours to maintain and would end any chance of taking upstream fixes.

## Consequences

- A reader finds every Cemengal change by `git grep "Cemengal"` plus the user's list in the concept page.
- New tools follow upstream's shape: a method on `AutoCADCOMServer`, an entry in `handle_list_tools`, a branch
  in `handle_call_tool` ([server](../modules/server.md)).
