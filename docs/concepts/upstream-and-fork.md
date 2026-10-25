---
title: "Upstream and fork — what is theirs, what is ours"
type: concept
updated: 2026-10-24
sources: [README.md, LICENSE, "git log upstream/main", autocad_mcp/server.py]
related: [../decisions/0001-minimal-marked-divergence-from-upstream.md, ../sources/commits/2025-07.md, ../sources/issues/CEM-EnriqueRuiz-CEM_API-82.md]
tags: [fork, upstream]
---

# Upstream and fork

| | |
|---|---|
| Upstream | `https://github.com/thepiruthvirajan/autocad-mcp-server`, remote `upstream` |
| Fork | `https://github.com/CEM-EnriqueRuiz/CEM_AutocadMCP`, remote `origin` |
| Licence | Apache-2.0 (`LICENSE`). Keep it and the attribution |
| Upstream state | six commits, 2025-07-20 to 2025-07-28, one author; no activity since ([sources](../sources/commits/2025-07.md)) |
| Local folder | `CEM_IA/CEM_AutocadMCP`, renamed from `autocad-mcp-server` on 2026-10-24 |

## What upstream left unfinished

- `server.py` advertised 21 tool entries but carried placeholder comments
  (`# [Include all other existing methods …]`) where nine methods should be: `delete_entities_by_handles`,
  `_by_type`, `_by_layer`, `_by_color`, `_by_type_and_color`, `delete_last_entities`, `delete_all_entities`,
  `undo_last_operation`, `change_entity_color`. Calling them raised `AttributeError`.
- `delete_entities_by_color` was listed twice.
- Every `Regen` used `constants.acActiveViewport`, empty without makepy, so it threw (and, inside
  `safe_operation`, made the create return `None`).
- `pyproject.toml`'s script pointed at `main`, a coroutine; the README configured Claude with `test_script.py`.
- Compiled `autocad_mcp/__pycache__/*.cpython-312.pyc` files are committed.

## What changed

**The user's rework, 2026-10-17/18 (before the fork, no `Cemengal` comments):** lazy connection, ProgID
discovery, `ACAD_*` settings, busy retries ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md));
the nine missing methods (`_snapshot_entities`, `_delete_where` and friends) and the duplicate removed;
`not_connected()` with the reason; `HandleToObject` in `delete_entity_by_handle`; `ACAD_REGEN_ALL` instead of
`constants`; `room`/`partition` mapped to `WALLS`; `get_drawing_info` reports application, version, ProgID and
open drawings; `run()` entry point; `mcp>=1.2,<2`; the README's Claude section; `setup_claude.*`,
`diag_com.*`, `live_test.*`, `.gitignore`.

**The Cemengal fork, 2026-10-24 (marked `# Cemengal`):**
- reads never modify the drawing: structure layers are created lazily ([0004](../decisions/0004-reads-never-modify-the-drawing.md));
- bounded listings, `entity.Update()` instead of a `Regen` per entity, delete by handle without a scan
  ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md));
- `create_or_get_layer` and `set_current_layer` say why they failed;
- the startup/open race (`AttributeError` from pywin32) is retried like any busy call (`is_busy`,
  `call_when_ready`), and no tool creates a drawing: with none open they answer "No drawing is open in
  AutoCAD…" instead of the user's `Documents.Add()` ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md),
  [0004](../decisions/0004-reads-never-modify-the-drawing.md));
- logs in the temp folder, the setup's ACC refusal, `autocad_mcp/temp_files.py`
  ([0003](../decisions/0003-no-writes-under-acc-or-beside-scripts.md));
- `live_test.py` rewritten as an MCP stdio client ([live test](../workflows/live-test.md));
- `pyproject.toml`: a `dev` extra with pytest, pytest settings;
- added `tests/`, `docs/`, `CLAUDE.md`, `AGENTS.md`, `.claude/`, `.agents/`, `.mcp.json`, `.gitattributes`.

`git grep -n "Cemengal" -- autocad_mcp pyproject.toml setup_claude.ps1 diag_com.py live_test.py` lists the code divergence.

## Syncing from upstream

```
git fetch upstream
git log --oneline main..upstream/main      # anything new?
git merge upstream/main                    # expect conflicts in server.py
```

Upstream has been silent since 2025-07-28. Never push to `upstream`.
