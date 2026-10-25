---
title: "CEM-EnriqueRuiz/CEM_API#82: the fork's first commit — nothing written under ACC, the onboarding, the live MCP runs"
type: source
updated: 2026-10-25
sources: [https://github.com/CEM-EnriqueRuiz/CEM_API/issues/82, autocad_mcp/server.py, autocad_mcp/temp_files.py, setup_claude.ps1, diag_com.py, live_test.py, pyproject.toml, README.md, tests/, "the user, 2026-10-24 and 2026-10-25"]
related: [../../index.md, ../../../../../docs/features/CEM-EnriqueRuiz-CEM_API-82.md, ../../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md, ../../decisions/0001-minimal-marked-divergence-from-upstream.md, ../../decisions/0002-lazy-connection-and-progid-discovery.md, ../../decisions/0003-no-writes-under-acc-or-beside-scripts.md, ../../decisions/0004-reads-never-modify-the-drawing.md, ../../decisions/0005-every-call-ends-inside-the-host-timeout.md, ../../concepts/upstream-and-fork.md, ../../concepts/known-gaps.md, ../../workflows/live-test.md, ../commits/2026-10.md]
tags: [issue, acc, logs, fork, bootstrap, cem_api, cross-repo]
---

# CEM-EnriqueRuiz/CEM_API#82

**Issue:** https://github.com/CEM-EnriqueRuiz/CEM_API/issues/82 ("Borrar logs in ACC de los MCP"). It lives in
CEM_API's tracker and its body is empty, so the spec is the user's request and decisions below. Cross-repo record:
the root [feature page](../../../../../docs/features/CEM-EnriqueRuiz-CEM_API-82.md).
- **Implemented:** 2026-10-24, in three dispatches from the coordinator (onboarding, audit and live test; plain
  AutoCAD; known gaps 12 and 13).
- **Committed:** 2026-10-25, as the fork's first Cemengal commit. It carries the user's own earlier uncommitted
  rework (2026-10-17/18) that this work built on, the onboarding, the 0031 audit and the fixes.

## What was asked

The user, 2026-10-24 (translated): "Test the MCPs of Navisworks, Civil 3D, AutoCAD and Revit with the files I left in
CEM_Test\MCP, and verify that no one writes logs or other files in an ACC path: I don't want any massive
synchronization through the ACC Desktop Connector. If we or the app need logs, they go to a local temp folder that
is cleaned automatically, without accumulating. Fix what you find." Root decision
[0031](../../../../../docs/decisions/0031-nothing-writes-under-acc-logs-in-local-temp.md).

The coordinator forked the repo to `CEM-EnriqueRuiz/CEM_AutocadMCP`, renamed the folder from `autocad-mcp-server`,
and asked for: the onboarding (the root's add-a-sibling-repo steps 2–4: skill, wiki, a test-first pytest suite),
keeping the user's uncommitted work; the audit of every file write against 0031, with a guard test; a live MCP run
through the stdio server on Civil 3D 2027 and then on plain AutoCAD 2027, creating and deleting entities and never
saving; and, after the plain AutoCAD run, "fix what the tests find" (known gaps 12 and 13).

## The user's decisions (2026-10-25) that concern this repo

- **Keep every pass-1 change.** Commit and push; the user's earlier rework goes in with it, since the work is theirs.
- **Only the MCPs were in question.** Root 0031 now says the rule has no exception for the MCPs, while add-ins keep
  the team files they write by design. This repo is an MCP server: it has no exception, and none was needed.
- **Doc drift stays reported:** upstream's README and the tracked `.pyc` files are not fixed in this commit
  ([known gaps](../../concepts/known-gaps.md) 7 and 8).
- The ACC clean-up (148 old Revit MCP files) and the menu publish are the coordinator's; nothing of this repo was
  ever on ACC.

## The user's rework (2026-10-17/18, before the fork)

**What was asked.** Make the upstream server work with the user's Civil 3D 2027 from Claude Desktop.
**What was done.** `GetActiveObject("AutoCAD.Application")` failed because the generic ProgID pointed at an
uninstalled release; `diag_com.py` found it. The server now connects lazily through every registered ProgID,
retries a busy AutoCAD, and never launches AutoCAD by default ([0002](../../decisions/0002-lazy-connection-and-progid-discovery.md)).
The nine advertised but missing tools were written, the duplicate tool removed, the `Regen` enum replaced by a
literal, the entry point fixed (`run()`), `mcp` pinned below 2. `setup_claude.ps1` builds the `.venv` and registers
the server; `live_test.py` checked the server class directly against Civil 3D (create a thick line, delete it).
These changes carry no `# Cemengal` comment; [upstream and fork](../../concepts/upstream-and-fork.md) lists them.

## Decisions taken while implementing (2026-10-24)

- **Onboarding:** `CLAUDE.md`, `AGENTS.md`, the `cem-autocadmcp-dev` agent and skill, the Codex redirect,
  `.claude/settings.json` (wiki hooks), `.claude/settings.local.json` and `.mcp.json` (the shared qmd server),
  `.gitattributes`, this wiki, and a pytest suite. Divergence rule
  [0001](../../decisions/0001-minimal-marked-divergence-from-upstream.md): mark every change `# Cemengal`; the user's
  earlier rework is listed instead of re-annotated.
- **The `.venv` after the rename:** its editable install still pointed at the old folder, so the server failed to
  import from any other working folder. `pip install -e .` fixed it; verified from `C:\` and by the live test
  starting the server from `%TEMP%`. Rejected: adding a `cwd` to Claude's config (the user's file, and it would
  hide the broken install).
- **File writes ([0003](../../decisions/0003-no-writes-under-acc-or-beside-scripts.md)):** the server wrote
  nothing; the three scripts wrote their logs beside themselves. They now log through the new
  `autocad_mcp/temp_files.py` (`TempFolder`), and `setup_claude.ps1` carries the same prune in PowerShell and
  refuses an ACC folder. The guard `tests/test_no_acc_writes.py` was red on `diag_com.py:42`,
  `live_test.py:16` and `setup_claude.ps1:5` before the fix. Rejected: console-only logs; editing Claude's
  config to stop `__pycache__`; calling the Python helper from the setup.
- **Reads modified the drawing ([0004](../../decisions/0004-reads-never-modify-the-drawing.md)):** connecting
  added eleven layers. Now a structure creates only its own layer, when it is drawn. Test-first: red with
  eleven layers added on a read.
- **Live, the first read timed out ([0005](../../decisions/0005-every-call-ends-inside-the-host-timeout.md)):**
  a 6,947-layer Civil 3D drawing made `get_drawing_info` run ~5 min. Added a 40 s budget and a 100-layer
  default to the listings, `entity.Update()` instead of a `Regen` per created entity (1.7–3 s each), and a
  scan-free, model-space-only delete by handle. Test-first: red on 27 regens and a model-space scan. Rejected:
  paging, a COM worker thread with timeouts.
- **Layer tools said nothing on failure:** `create_or_get_layer` and `set_current_layer` returned a bare
  `success: false`; they now say whether AutoCAD is not connected or the layer is the problem. Found by the
  tool-contract test.
- **Claude's config moved:** since 2026-10-20 the Store app keeps it in `%LOCALAPPDATA%\Claude-Data\claude_<id>`,
  which `setup_claude.ps1` did not search; a re-run would have created an unread config. `Get-ClaudeConfigs`
  now searches it first. Test-first, in PowerShell against scratch folders.
- **`live_test.py` became an MCP client** that starts the server as Claude's config says and checks its own
  handles, not totals, because another agent shares the session ([live test](../../workflows/live-test.md)).
- **Plain AutoCAD 2027 (the second dispatch).** Launched as its shortcut does (`/product ACAD`), alone on the
  machine. No security prompt for `CEM_Civil3DMCP.bundle` (it declares `Platform="Civil3D"`). Differences from
  Civil 3D recorded in the [live test](../../workflows/live-test.md): the application name, proxies with `AeccDb*`
  object names, `Saved` false straight after the read-only open, a startup race where property reads raise
  `AttributeError` (pywin32 swallows the rejected name lookup), and a Start tab with no document. First recorded
  as [known gaps](../../concepts/known-gaps.md) 12 and 13, because neither affected an MCP call and the second was
  the user's design; superseded the same day by the fixes below, at the coordinator's request.
- **The race, known gap 12 ([0002](../../decisions/0002-lazy-connection-and-progid-discovery.md)).** `is_busy(error)`
  classifies a refused call: a `com_error` with `RPC_E_CALL_REJECTED` / `RPC_E_SERVERCALL_RETRYLATER`, or an
  `AttributeError` raised in a COM dispatch's `__getattr__` whose object, asked again for the same name through
  `_oleobj_.GetIDsOfNames`, is still refusing or knows the name by now. `call_when_ready` retries it within the
  existing budget (20 × 0.25 s); `safe_operation` and the connection's reads use it. Red first: connecting
  through `RacyDispatch` failed with "no usable drawing: AutoCAD.Application.26.Documents". A mutant treating
  every `AttributeError` as busy was caught by the two "not retried" tests. Rejected: retrying every
  `AttributeError` (a misspelt property would spend 5 s and lose its message); matching the message text
  `<object>.<name>` alone (the same text means a real missing property); makepy early binding (writes a
  generated cache to disk, and pins one AutoCAD release's type library).
- **The Start tab, known gap 13 ([0004](../../decisions/0004-reads-never-modify-the-drawing.md)).**
  `connect_to_autocad` no longer calls `Documents.Add()`; with no drawing open every tool answers `NO_DRAWING`
  ("No drawing is open in AutoCAD. Ask the user to open or create one in AutoCAD, then retry."), also with
  `ACAD_AUTOSTART=1`. Red first: the fake recorded the `Add()`. Rejected: adding a drawing for write tools only; a
  `new_drawing` tool nobody asked for.

## Files in the commit

- **The user's earlier work, with the `# Cemengal` changes on top:** `autocad_mcp/server.py`, `pyproject.toml`,
  `README.md`, `diag_com.py`, `live_test.py`, `setup_claude.ps1`, and the user's `diag_com.bat`, `live_test.bat`,
  `setup_claude.bat`.
- **New:** `autocad_mcp/temp_files.py`; `tests/` (`conftest.py`, `fake_acad.py` and nine test files);
  `docs/` (this wiki); `CLAUDE.md`, `AGENTS.md`, `.claude/agents/cem-autocadmcp-dev.md`,
  `.claude/skills/cem-autocadmcp-dev/SKILL.md`, `.agents/skills/cem-autocadmcp-dev/SKILL.md`,
  `.claude/settings.json`, `.claude/settings.local.json` (tracked in every workspace repo, though the user's global
  git ignore lists it), `.mcp.json`, `.gitignore`, `.gitattributes`.
- **Left out:** `.venv/` (the local install), `__pycache__/` and `.pytest_cache/` (generated), the three old dev logs
  `diag_log.txt`, `live_test_log.txt` and `setup_log.txt` (2026-10-17/18, ignored, for the user to delete), and the
  tracked upstream `autocad_mcp/__pycache__/*.cpython-312.pyc`, which stay tracked and unchanged
  ([known gaps](../../concepts/known-gaps.md) 8).

## Verification

- **Tests:** `.venv\Scripts\python.exe -m pytest -q`: 57 passed (44 after the first dispatch, 13 more for gaps 12
  and 13). The root runner's target is `autocadmcp` ([test](../../workflows/test.md)).
- **Live through MCP stdio,** with the server started as Claude Desktop's config says, from `%TEMP%`, on
  `CEM_Test\MCP\X-C3D-CSLZ-25012720_SERVICE PROP_CORR.dwg` (6,947 layers, 958 entities):
  - Civil 3D 2027: the first run timed out on `get_drawing_info` (60 s), which led to
    [0005](../../decisions/0005-every-call-ends-inside-the-host-timeout.md); the second passed every check in 17 s.
    The budget stopped listings at 40.1 s with `truncated` set.
  - Plain AutoCAD 2027, the drawing opened read-only: every check passed in 19 s; the budget gave 590 of 958
    entities and 752 layers. AutoCAD closed the drawing unsaved and quit with no prompt.
  - Both runs: the layers and entity count unchanged afterwards, only our own handles created and deleted, the
    drawing never saved (its modified time still 2026-10-20 18:16:48).
- **Not run live:** the gap 12 and 13 fixes (the AutoCAD slot had moved to Revit; the fake COM objects cover them),
  and the tools in [known gaps](../../concepts/known-gaps.md) item 4.
- **The ACC watcher:** no event from this repo's runs. During the Civil 3D runs it recorded 66 `Changed` events,
  all on old files under the Revit `05-CEMAIModeler` folder (someone reading them, which downloads), none naming
  AutoCAD, a `.dwg` or this repo, and none inside the MCP sessions. During the plain AutoCAD run (21:33:58–21:40:30)
  it recorded nothing at all.

## Left open

- The tools in [known gaps](../../concepts/known-gaps.md) item 4 have not run live; gaps 12 and 13 are fixed but not
  rechecked live.
- The tracked upstream bytecode (gap 8) and upstream's README (gap 7): doc drift, reported.
