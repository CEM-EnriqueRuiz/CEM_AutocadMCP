---
title: "Known gaps — what is missing, unverified or risky"
type: concept
updated: 2026-11-05
sources: [autocad_mcp/server.py, README.md, live_test.py, "live runs 2026-10-24", ".venv/Lib/site-packages/win32com/client/dynamic.py", tests/test_busy_race.py, tests/test_no_drawing.py]
related: [../modules/server.md, export-schema.md, ../concepts/com-connection.md, ../workflows/live-test.md, ../decisions/0005-every-call-ends-inside-the-host-timeout.md]
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
8. **Closed 2026-11-05: committed bytecode.** `autocad_mcp/__pycache__/*.cpython-312.pyc` came from upstream and
   were tracked (unchanged in the fork's first commit, #82, on the coordinator's instruction). The maintenance review
   of 2026-11-05 deleted them: bytecode of upstream's 2025 `server.py`, which the `.venv`'s Python 3.13 never loads.
   `.gitignore` ignores the ones the interpreter writes.
9. **`__pycache__` is written beside the modules** by the Python interpreter. Harmless on a local checkout; it
   would sync if the repo were ever run from ACC, which the setup refuses
   ([0003](../decisions/0003-no-writes-under-acc-or-beside-scripts.md)).
10. **`test_script.py` modifies the active drawing** and does not clean up ([scripts](../modules/scripts.md)).
11. **Closed 2026-11-05: the three old dev logs** (`diag_log.txt`, `live_test_log.txt`, `setup_log.txt`,
    2026-10-17/18) were moved out of the repo by the maintenance review (root
    [0037](../../../../docs/decisions/0037-code-follows-the-tables.md): nothing temporary stays in a repo), and their
    `.gitignore` lines went with them. No script writes beside itself (`tests/test_no_acc_writes.py`).
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
14. **`export_drawing` run live once, on one drawing** (2026-11-01, plain AutoCAD 2025, 68,798 entities, 685–795
    entities/s; [live test](../workflows/live-test.md)). Not yet on Civil 3D, AutoCAD 2027, or in a session shared
    with another tool; the computed architectural texts were checked for shape, not against AutoCAD's rendering.
    Some dimensions refuse `Measurement` ("object not open for write": 22 of 3,152) and a 2D polyline refused
    `GetBulge`; both land in `errors`, and the dimension's displayed text is then the override or `null`.
15. **What the export cannot get over ActiveX:** a viewport's view centre and frozen layers, every dimension-line
    point, the extension-line points of rotated (linear) dimensions, and the defining points of radial, diametric
    and ordinate dimensions (AutoCAD 2025's type info, live 2026-11-01), and the text a dimension
    actually renders: it is computed from the dimension's format settings and flagged approximate for
    architectural, fractional, engineering and Windows units, DMS, arc symbols and tolerances. Also not exported:
    hatches, solids, meshes, images and Civil 3D objects (counted as skipped with the reason). An AutoLISP
    `entget` reader would close the first three; phase 2, decided after the live measurement
    ([schema](export-schema.md), [0006](../decisions/0006-background-export-jobs.md)).
16. **Closed 2026-11-01: an export over 50 MB lived only until the next server start.** The folder-wide size cap
    deleted a 53.7 MB export of a real drawing. `exports\` now has its own rule: the newest export and the newest
    complete one are never pruned, the others stay up to 3 files and 7 days, outside the 50 MB cap; a fresh
    process's prune of the real folder kept the 50.0 MB export ([temp-files](../modules/temp-files.md),
    [0006](../decisions/0006-background-export-jobs.md)).
17. **A junction swapped in at the last moment is narrowed, not closed** (2026-11-01, SEC-1). Between the prune's
    last check and its delete, or between `_prepare`'s second check and the caller's write, a junction swapped in is
    a race the re-checks narrow but cannot close (Windows offers no delete- or create-relative-to-a-handle in
    Python's standard library). The steady case is closed: the prune follows no reparse point, and `log_path` /
    `artefact_dir` refuse a junctioned `Cemengal`, root or artefact folder, so `export_drawing` answers "Cannot write
    the export: Refusing to write through a junction or link…" instead of writing
    ([0003](../decisions/0003-no-writes-under-acc-or-beside-scripts.md) point 6); `setup_claude.ps1` refuses the same
    before writing its transcript.
18. **`delete_entity_by_handle` is not bounded to model space** (found 2026-11-05 by the maintenance review, with the
    fakes; not run live). Unlike `delete_entities_by_handles`, it deletes whatever object `HandleToObject` returns,
    so the handle of a layer, a block definition or a style deletes that object when AutoCAD allows it; the fake
    lost a layer this way and the tool answered `success`. When `HandleToObject` fails it scans model space
    (case-sensitive), as slow as a bulk delete (item 1); after the delete it `Regen`s (one entity took 1.37–1.45 s live on
    2026-10-24, six took 0.15–0.17 s through the plural); and `safe_operation`'s `None` is ignored, so a refused delete still answers `success`.
    The fix proposed to the user: the plural's path ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md),
    [server](../modules/server.md)).
