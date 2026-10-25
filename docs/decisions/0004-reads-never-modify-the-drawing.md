---
title: "0004 — A read never modifies the drawing; no tool saves one or creates one"
type: decision
status: current
updated: 2026-10-24
sources: [autocad_mcp/server.py, tests/test_reads_do_not_modify.py, tests/test_no_drawing.py, live_test.py]
related: [../modules/server.md, ../workflows/live-test.md, 0003-no-writes-under-acc-or-beside-scripts.md]
tags: [drawing, layers, safety]
---

# 0004 — A read never modifies the drawing; no tool saves one or creates one

## Context

Upstream's `connect_to_autocad()` called `ensure_structure_layers()`, which adds eleven layers (`WALLS`, `DOORS`,
`WINDOWS`, `FURNITURE`, `ELECTRICAL`, `PLUMBING`, `HVAC`, `STRUCTURE`, `ANNOTATION`, `SITE`, `UTILITIES`) to the
drawing. Connecting happens on the first tool call, so a plain `get_drawing_info` on a client's Civil 3D drawing
left eleven new layers in it and marked it modified. The live test of 2026-10-24 had to leave the test drawing
as it found it.

## Decision

- Connecting adds nothing. `ensure_structure_layer(name)` creates one predefined layer, and only
  `create_structure` (its own layer) and `add_structure_label` (`ANNOTATION`) call it, just before they use it.
- Basic entities (`create_line`, `create_circle`, …) go on the current layer, as upstream did, and add no layer.
- **No tool creates a drawing** (added 2026-10-24). With no drawing open (plain AutoCAD on its Start tab, or
  after the user closes the last one), every tool answers `{"error": "No drawing is open in AutoCAD. Ask the user
  to open or create one in AutoCAD, then retry."}` (`NO_DRAWING`), so the agent asks the user. This replaced the
  user's 2026-10-17 `Documents.Add()` in `connect_to_autocad`, which opened a blank drawing on the first tool
  call, even a read. It holds with `ACAD_AUTOSTART=1` too: launching AutoCAD is not asking for a drawing.
- No tool saves, exports or `WBLOCK`s the drawing. The user's drawing, saved where the user chooses, is the
  user's data ([0003](0003-no-writes-under-acc-or-beside-scripts.md)).
- `ensure_structure_layers()` stays, unused, as upstream's method.

**Rejected:** deleting the layers after a read (a second modification, and a layer in use cannot be deleted);
a `create_structure_layers` tool (nobody asked; `create_structure` already makes the one it needs). For the
Start tab: keeping `Documents.Add()` for write tools only (a write would still create a drawing the user did not
ask for, and leave it unsaved); a `new_drawing` tool (nobody asked; it is the one write that could create a
drawing explicitly, and can be added if the user wants it).

## Consequences

- `tests/test_reads_do_not_modify.py` pins it with a fake COM drawing: reads add no layer; a wall adds only
  `WALLS`; a labelled door adds `DOORS` and `ANNOTATION`; the current layer is restored.
- `tests/test_no_drawing.py` pins the Start tab with `FakeApp(empty=True)`: reads, creates, structures, deletes
  and zoom all answer `NO_DRAWING` and add no document; a drawing the user opens later is found; closing the
  last drawing gives the same answer.
- Live, 2026-10-24: the X-C3D Civil 3D drawing kept its 6,947 layers through `get_drawing_info`, and its
  `Saved` flag stayed true until the test created entities. Creating and deleting entities still sets the
  flag; there is no COM way to clear it short of saving, so the session is closed without saving.
