---
title: "Known gaps — what is missing, unverified or risky"
type: concept
updated: 2026-10-25
sources: [autocad_mcp/server.py, README.md, live_test.py, "live runs 2026-10-24", ".venv/Lib/site-packages/win32com/client/dynamic.py", tests/test_busy_race.py, tests/test_no_drawing.py]
related: [../modules/server.md, ../concepts/com-connection.md, ../workflows/live-test.md, ../decisions/0005-every-call-ends-inside-the-host-timeout.md]
tags: [gaps, risks]
---

# Known gaps

1. **Bulk deletes scan model space.** `delete_entities_by_type`, `_by_layer`, `_by_color`, `_by_type_and_color`,
   `delete_last_entities` and `delete_all_entities` read every entity over COM (~16–65 ms each), so on a large
   drawing they can outlive the client's 60 s; the server keeps deleting after the client gives up. Not run live.
2. **`undo_last_operation` is not ours to undo.** It sends AutoCAD's `U`, which undoes the last operation in the
   document, whoever made it; one MCP call can be several AutoCAD operations. Not run live (shared session).
3. **AutoCAD and Civil 3D together.** Both were tested live, one at a time (2026-10-24,
   [live test](../workflows/live-test.md)). With both running, both register `AutoCAD.Application.26`, and COM
   picks the first in the Running Object Table; `ACAD_PROGID` cannot tell them apart.
4. **Tools not run live:** `create_structure`, `create_rectangle`, `create_or_get_layer`, `set_current_layer`,
   `zoom_extents`, `undo_last_operation` and the bulk deletes (they change layers, the view, or the user's
   entities). They are covered only by the fake-COM tests.
5. **`get_entities` has no paging.** On a large drawing it returns what fits in 40 s with `truncated: true`; there
   is no `start_index` to fetch the rest ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md)).
   Its result also repeats each entity in `entities` and `entities_by_layer` (upstream shape), doubling its size.
6. **Errors inside a create are swallowed.** When `safe_operation` fails it returns `None`, and the create still
   answers `success: true` with a placeholder handle (`"line_main"`, `"text_created"`); the real reason is in
   `last_error`, which only `not_connected()` reports. Upstream behaviour.
7. **Upstream README is aspirational.** It documents tools and arguments that differ from the code (for example
   `create_or_get_layer` with a `name` argument, `delete_entities_by_handles` as a batch example before it
   existed) and an `autocad_mcp.AutoCADCOMServer` import that the package does not export. The code and this
   wiki win; the README's Claude Desktop section is current.
8. **Committed bytecode.** `autocad_mcp/__pycache__/*.cpython-312.pyc` came from upstream and are tracked;
   `.gitignore` ignores new ones. They stayed tracked and unchanged in the fork's first commit (#82, 2026-10-25),
   on the coordinator's instruction; remove them from the index in a change of their own (`git rm --cached`).
9. **`__pycache__` is written beside the modules** by the Python interpreter. Harmless on a local checkout; it
   would sync if the repo were ever run from ACC, which the setup refuses
   ([0003](../decisions/0003-no-writes-under-acc-or-beside-scripts.md)).
10. **`test_script.py` modifies the active drawing** and does not clean up ([scripts](../modules/scripts.md)).
11. **The three old dev logs** (`diag_log.txt`, `live_test_log.txt`, `setup_log.txt`, 2026-10-17/18) are still
    beside the scripts, untracked and ignored, for the user to delete.
12. **Closed 2026-10-24: a busy AutoCAD surfacing as `AttributeError`.** pywin32's late binding
    (`win32com/client/dynamic.py`, `__getattr__`) swallows a refused name lookup and raises
    `AttributeError("<object>.<name>")`; seen live right after launching plain AutoCAD and during
    `Documents.Open`. `is_busy` now recognises that race (it re-asks the same object for the same name) and
    `call_when_ready` retries it within the busy budget, in `safe_operation` and in the connection's own reads; a
    real missing property still fails at once ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md),
    `tests/test_busy_race.py`). Other direct property reads outside `safe_operation` (for example inside
    `get_drawing_info`'s per-field `try` blocks) are not retried: once connected, the race is over.
13. **Closed 2026-10-24: connecting on the Start tab added a drawing.** `connect_to_autocad` no longer calls
    `Documents.Add()`; with no drawing open every tool answers "No drawing is open in AutoCAD…"
    ([0004](../decisions/0004-reads-never-modify-the-drawing.md), `tests/test_no_drawing.py`).
