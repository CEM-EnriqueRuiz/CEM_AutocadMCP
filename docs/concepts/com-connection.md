---
title: "COM connection — ProgIDs, the Running Object Table, busy AutoCAD, slow calls"
type: concept
updated: 2026-10-24
sources: [autocad_mcp/server.py, diag_com.py, "live measurements 2026-10-24"]
related: [../decisions/0002-lazy-connection-and-progid-discovery.md, ../decisions/0005-every-call-ends-inside-the-host-timeout.md, ../modules/server.md, known-gaps.md]
tags: [com, autocad, civil3d]
---

# COM connection

The server is an out-of-process COM client of `acad.exe`. Everything it does is a cross-process call
marshalled onto AutoCAD's main thread.

## Finding AutoCAD

- A running AutoCAD registers its `Application` in the Running Object Table under its CLSID, e.g.
  `!{E76F49EB-7DAE-4682-ADE6-6C12ECA76DD7}` for release 26 (2027).
- `GetActiveObject(progid)` resolves the ProgID to a CLSID through the registry, then looks it up in the table.
  The generic `AutoCAD.Application` follows `CurVer`, which an uninstall can leave pointing at a missing
  release: on 2026-10-17 it was `AutoCAD.Application.23` and failed with "Operation unavailable"
  (`-2147221021`, `MK_E_UNAVAILABLE`) while `.26` worked. On 2026-10-24 the generic one resolved again.
  `candidate_progids()` covers both ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md)).
- Civil 3D is AutoCAD underneath: the same `acad.exe` with `/product C3D`, the same ProgID
  (`AutoCAD.Application.26`), `Application.Name` "Autodesk Civil 3D 2027". Plain AutoCAD is `/product ACAD` and
  names itself "AutoCAD". The server's tools are plain AutoCAD ones and work on both; in plain AutoCAD the Civil
  objects are proxies that still report their `AeccDb*` `ObjectName` ([live test](../workflows/live-test.md)).
- Right after launch, or while a drawing opens, a property read can fail with `AttributeError` instead of a
  busy error: pywin32 swallows the refused name lookup. `is_busy` treats that race as busy
  ([0002](../decisions/0002-lazy-connection-and-progid-discovery.md)).
- On its Start tab AutoCAD has no drawing at all; the server then answers "No drawing is open in AutoCAD…" and
  never creates one ([0004](../decisions/0004-reads-never-modify-the-drawing.md)).
- `diag_com.py` prints all of this when a connection fails.

## A busy AutoCAD

While a command or modal dialog runs, AutoCAD rejects calls with `RPC_E_CALL_REJECTED` or
`RPC_E_SERVERCALL_RETRYLATER`, and while it starts or opens a drawing the first lookup of a name can come back
as pywin32's `AttributeError` instead. `is_busy` recognises both; `call_when_ready` retries them for about 5 s
(`BUSY_RETRIES` × `BUSY_WAIT`), for `safe_operation` and for the connection's reads; other errors are kept in
`last_error` and the operation returns `None`.

## Slow calls

Measured on 2026-10-24 (Civil 3D 2027, a 6,947-layer, 958-entity drawing, with another agent's plugin in the
same session): ~10–65 ms per property read, 1.7–3 s per `Regen`. Treat every COM call as expensive: loop over
handles, not over model space, and bound any listing ([0005](../decisions/0005-every-call-ends-inside-the-host-timeout.md)).

## A shared session

Another tool can drive the same AutoCAD at the same time (the CEM_Civil3DMCP plugin listens on port 8080 inside
it). Consequences: entity counts can move under you, so check your own handles, not totals; never send
`undo_last_operation` (AutoCAD's `U` undoes the last operation, whoever made it); expect more busy retries.
