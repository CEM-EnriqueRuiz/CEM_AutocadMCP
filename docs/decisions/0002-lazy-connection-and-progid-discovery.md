---
title: "0002 — Connect lazily, through every registered AutoCAD ProgID"
type: decision
status: current
updated: 2026-10-24
sources: [autocad_mcp/server.py, diag_com.py, tests/test_com_connection.py, tests/test_tool_contract.py, tests/test_busy_race.py, ".venv/Lib/site-packages/win32com/client/dynamic.py"]
related: [../concepts/com-connection.md, ../modules/server.md, ../modules/scripts.md]
tags: [com, connection, progid]
---

# 0002 — Connect lazily, through every registered AutoCAD ProgID

## Context

Upstream connected in `main()` before the MCP handshake, with `GetActiveObject("AutoCAD.Application")`, and
fell back to `Dispatch`, which launches AutoCAD. On the user's machine (2026-10-17) that failed: the generic
ProgID's `CurVer` pointed at `AutoCAD.Application.23`, a release no longer installed, while the running Civil 3D
2027 registered itself as `AutoCAD.Application.26` (`diag_com.py` showed the Running Object Table). Launching
AutoCAD from the server also made Claude Desktop's startup time out.

## Decision

This is the user's rework (2026-10-17/18), kept as the fork's baseline:

- **Lazy.** `main()` only registers the tools. The first tool call connects (`ensure_connection`), so the
  handshake never waits on AutoCAD. Every call re-reads `ActiveDocument`, so the server follows the drawing the
  user is looking at.
- **Every ProgID.** `candidate_progids()` tries the generic `AutoCAD.Application`, then every registered
  `AutoCAD.Application.<n>`, newest first. `ACAD_PROGID` forces one.
- **No launch by default.** With no running AutoCAD a tool returns "Not connected to AutoCAD … (detail: …)",
  naming each ProgID's error. `ACAD_AUTOSTART=1` restores the launch.
- **Busy retries.** `safe_operation` retries `RPC_E_CALL_REJECTED` / `RPC_E_SERVERCALL_RETRYLATER` (AutoCAD in a
  command or dialog) 20 times, 0.25 s apart, and pauses `ACAD_OP_DELAY` (0.05 s) after each call instead of
  upstream's fixed 1 s.
- **The startup and open race is busy too** (Cemengal, 2026-10-24). Right after AutoCAD starts, and while it
  opens a drawing, the *first lookup of a property name* on a COM object comes back as
  `AttributeError('<object>.<name>')`: pywin32's late binding (`win32com.client.dynamic.CDispatch.__getattr__`)
  swallows the refused `GetIDsOfNames`. `is_busy(error)` recognises it: for an `AttributeError` raised in a
  dispatch's `__getattr__`, it asks that object's `_oleobj_.GetIDsOfNames` for the same name again; refused
  (busy) or known by now means the race, `DISP_E_UNKNOWNNAME` means a real missing property. `call_when_ready`
  retries what `is_busy` accepts within the same budget (`BUSY_RETRIES` 20 × `BUSY_WAIT` 0.25 s); `safe_operation`
  and the connection's own reads (`Documents.Count`, `ActiveDocument`, `Name` in `connect_to_autocad` and
  `ensure_connection`) go through it. Running out of budget says "AutoCAD stayed busy".

**Rejected:** fixing the registry's `CurVer` (machine-wide, needs admin, and breaks again on the next install);
connecting at startup with a timeout (still delays the handshake). For the race: retrying every
`AttributeError` (a typo in a property name would cost the whole 5 s budget and hide the real message); early
binding with makepy (`gencache.EnsureDispatch` turns lookups into compile-time ids, but it writes a generated
type-library cache to disk on first use, against [0003](0003-no-writes-under-acc-or-beside-scripts.md), and pins
one AutoCAD release's type library).

## Consequences

- Plain AutoCAD 2027 and Civil 3D 2027 register the same ProgID. With both running, COM returns whichever
  registered first in the Running Object Table ([known gaps](../concepts/known-gaps.md)).
- `tests/test_com_connection.py` pins the ordering, the forced ProgID, the fall-through past a stale generic
  ProgID, the refusal to launch, the busy retry and following the active drawing; `test_tool_contract.py`
  checks the handshake does not connect. `tests/test_busy_race.py` pins the race with `fake_acad.RacyDispatch`,
  a stand-in that fails its first lookups the way pywin32 does: retried while connecting and in
  `safe_operation`, bounded, and never for a missing property or a plain Python `AttributeError`.
