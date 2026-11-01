---
title: "export — autocad_mcp/export.py and export_text.py, the background drawing export"
type: module
updated: 2026-11-01
sources: [autocad_mcp/export.py, autocad_mcp/export_text.py, autocad_mcp/server.py, tests/test_export_jobs.py, tests/test_export_schema.py, tests/test_com_reader.py, tests/test_com_reader_real.py, tests/test_export_text.py]
related: [../decisions/0006-background-export-jobs.md, ../concepts/export-schema.md, server.md, temp-files.md, ../concepts/com-connection.md]
tags: [module, export, com, threading]
---

# export: `autocad_mcp/export.py`, `autocad_mcp/export_text.py`

Cemengal-only files behind `export_drawing`, `get_export_status` and `cancel_export`
([0006](../decisions/0006-background-export-jobs.md)); the file they write: [export schema](../concepts/export-schema.md).

## `export.py`

| Member | Contract |
|---|---|
| `Limits(max_entities, max_seconds, max_bytes, block_depth, busy_patience)` | defaults from `ACAD_EXPORT_*` (below); `Limits.given(**kw)` keeps the defaults for `None` |
| `ComReader(is_busy, patience, wait, checkpoint, on_wait, raw_types)` | `get(obj, name, kind)` / `call(obj, name, *args, kind)`: a raw `IDispatch` (or a CDispatch's `_oleobj_`) goes through the DISPID cache keyed `(kind, name)` and its results stay raw; anything else is read with `getattr` (the fakes). An unknown member raises `Unavailable` (cached). Busy calls are retried until `patience`, then `Busy`; `checkpoint()` runs between waits |
| `read_drawing(app, doc, limits, …)` / `DrawingReader` | the walk: header, layouts (model first, then tab order), each space's entities by `Item(i)`, then the referenced block definitions breadth-first with a visited set and `block_depth`; one reader per `ObjectName`; counts every entity. `check()` before each entity raises `Cancelled` or `LimitReached` |
| `ExportJob` | `running` → `done` / `failed` / `cancelled`; the first final state stays; `status()` is thread-safe; a reason is one line |
| `ExportJobs(temp, is_busy, clock, now)` | `start(app, document, full_name, limits)` (marshals only once accepted; releases the stream if the thread cannot start), `status(id)`, `cancel(id)`, `join(id, timeout)`; one running job at a time; `_run` is the thread: `CoInitialize`, the proxy, `find_document`, the walk, the size check, `.partial` → `os.rename`, then `TempFolder.prune_exports` (the last 3, [temp-files](temp-files.md)) |
| `app_opener(app)` → `AppOpener` | marshals the server's `Application` for the thread (`CoMarshalInterThreadInterfaceInStream`); calling it or `release()` consumes the stream once; a fake is shared |
| `reserve(folder, document, now)` | `(final, failed, partial)`; never a name already used by a `.json` or `.failed.json` |
| `safe_stem(name)` | the stem only, reserved characters replaced; over `MAX_STEM` (80): a 71-character prefix + `~` + 8 hex of its SHA-1 (QA-8) |

The server holds one `ExportJobs` (`self.exports`). `export_drawing` connects, finds the document (the active one,
or one named by name or full path among the open ones; otherwise it lists them), and starts the job.

## `export_text.py`

Pure: `text_plain` (TEXT `%%` codes), `mtext_plain` (MText codes, `\P`/`\X` new lines, stacks as `a/b`, escapes),
`format_decimal`, `format_linear`, `format_angle`, `displayed_text(dim_type, measurement, override, fmt)` and the
enum maps (`AcDimLUnits`, `AcDimUnits` → `ALT_TO_LINEAR`, `AcAngleUnits`). The rule is on the
[schema page](../concepts/export-schema.md#the-displayed-text-rule-export_textdisplayed_text).

## Settings (environment)

| Variable | Default | Effect |
|---|---|---|
| `ACAD_EXPORT_MAX_ENTITIES` | `200000` | fail beyond this many entities (spaces and block definitions together) |
| `ACAD_EXPORT_MAX_SECONDS` | `3600` | fail after this long |
| `ACAD_EXPORT_MAX_BYTES` | `104857600` | fail when the file would be larger |
| `ACAD_EXPORT_BLOCK_DEPTH` | `4` | nesting followed in block definitions; deeper ones go to `blocks_not_read` |
| `ACAD_EXPORT_BUSY_PATIENCE` | `300` | seconds to wait for a busy AutoCAD on one call before failing |

The tool arguments override the first four per job.

## Gotchas

- Key the DISPID cache by object type: two interfaces may number the same name differently. `ObjectName` itself
  is read with kind `AcDbObject` (inherited from `IAcadObject` by every entity); a block record's members with
  `Block:<name>`, because model space, paper spaces and definitions are different interfaces.
- Never call the server's proxy from the job's thread: marshal it (`app_opener`). An in-process COM object
  marshalled this way calls back into the creating thread, which must pump messages
  (`tests/test_com_reader_real.py` does); AutoCAD is out of process, so its proxy calls `acad.exe` directly.
- An `AttributeError` raised inside a fake's property reads as `Unavailable`; on real COM only
  `DISP_E_UNKNOWNNAME` / `DISP_E_MEMBERNOTFOUND` do.
