---
title: "0005 — Every tool call ends inside the host's 60 s, even on a large drawing"
type: decision
status: current
updated: 2026-10-24
sources: [autocad_mcp/server.py, tests/test_time_budget.py, live_test.py, "live measurements, 2026-10-24, Civil 3D 2027, X-C3D-CSLZ-25012720_SERVICE PROP_CORR.dwg"]
related: [../modules/server.md, ../concepts/com-connection.md, ../workflows/live-test.md, ../concepts/known-gaps.md]
tags: [performance, timeout, com]
---

# 0005 — Every tool call ends inside the host's 60 s, even on a large drawing

## Context

The first live MCP run (2026-10-24) on a real Civil 3D drawing, 6,947 layers and 958 entities, failed on the
very first tool: `get_drawing_info` did not answer within the client's 60 s, the same limit Claude Desktop
applies. Measured through COM on that drawing, with AutoCAD shared with another agent:

| Operation | Cost |
|---|---|
| read one layer (name, colour, frozen, locked) | ~45 ms → all layers ~5 min |
| read one entity (type, layer, handle, colour, visible) | ~65 ms → all entities ~62 s |
| `ModelSpace.Item(i).Handle` (the scan behind a delete by handle) | ~16 ms → ~15 s per delete call |
| `Regen` (all viewports / active viewport) | 1.7 s / 3.0 s, once per created entity |
| `HandleToObject` | ~46 ms |

Upstream called `Regen` after every created entity, but through `constants.acActiveViewport`, which is empty
without makepy, so it always threw and never ran. The user's 2026-10-17 fix made it run, and a thick line
(four entities) then cost four regens.

## Decision

- **A time budget for listings.** `TOOL_BUDGET` (`ACAD_TOOL_BUDGET`, default 40 s) bounds `get_drawing_info`'s
  layer list and `get_entities`. When it stops early it says so: `layers_truncated` / `truncated: true`.
- **`get_drawing_info` lists at most `max_layers` layers (default 100)**, a new optional argument; `total_layers`
  still gives the count. 6,947 layers would also be ~500 KB of tool result for the model to read.
- **`entity.Update()` instead of `doc.Regen()`** after each created entity (`show()`): it redraws that entity only.
- **`delete_entities_by_handles` looks each handle up** with `HandleToObject`, and deletes it only when model
  space owns it (`OwnerID == ModelSpace.ObjectID`), instead of scanning model space. A handle of a layer or
  any other non-entity is reported in `not_found`, never deleted.

**Rejected:**
- Paging (`start_index`) for `get_entities`: not needed for the reported break, and a new contract; `max_entities`
  plus `truncated` already tell the caller. Revisit if an agent needs the whole list of a large drawing.
- Running COM on a worker thread with a per-call timeout: COM objects are apartment-bound, and a timed-out
  call would keep running inside AutoCAD anyway.
- Dropping the per-call `OP_DELAY` to 0: it is 0.05 s and protects a busy AutoCAD; not the cost here.

## Consequences

- Live after the change, through MCP: `get_drawing_info` 4.0 s (100 layers); `get_entities` of all 958 stops
  at 40.1 s with 745 and `truncated: true`; `get_drawing_info(max_layers=10000)` stops at 40.1 s with 977;
  a thick line 0.54 s; `delete_entities_by_handles` of six handles 0.15 s.
- The other bulk deletes (`by_layer`, `by_type`, `by_color`, `by_type_and_color`, `last`, `all`) still scan
  model space and can exceed 60 s on a large drawing ([known gaps](../concepts/known-gaps.md)).
- `tests/test_time_budget.py` pins the layer cap, both budgets, no `Regen` on create, and the scan-free,
  model-space-only delete by handle.
- A whole-drawing read does not fit any budget: it runs as a background job whose tools answer at once
  ([0006](0006-background-export-jobs.md), 2026-11-01).
