---
title: "Export schema v1 — what export_drawing writes"
type: concept
updated: 2026-11-01
sources: [autocad_mcp/export.py, autocad_mcp/export_text.py, tests/test_export_schema.py, tests/test_export_text.py, tests/export_drawing_fake.py]
related: [../decisions/0006-background-export-jobs.md, ../modules/export.md, known-gaps.md]
tags: [export, schema, dimensions, json]
---

# Export schema v1

One UTF-8 JSON object per file, compact (no indentation) ([0006](../decisions/0006-background-export-jobs.md)). Points are `[x, y, z]`
lists of floats, angles are radians, lengths are drawing units (`drawing.insunits`). A field ActiveX does not give
is `null` and its name is in the record's `unavailable` list; a property that failed is `null` and its message is
in `errors`. Nothing is dropped silently: every entity is listed, read or skipped, and counted.

## Top level

| Key | Content |
|---|---|
| `schema`, `schema_version` | `"cemengal.autocad.export"`, `1` |
| `complete` | `true`; a `.failed.json` has `false`, `state`, `reason`, `progress`, `counts` instead of the content |
| `export` | `started_at`, `elapsed_s`, `entities_read`, `entities_per_second`, `com_calls`, `busy_waits`, `limits` |
| `application` | `name`, `version` (AutoCAD or Civil 3D, the session's release) |
| `drawing` | `name`, `full_path`, `version` (`ACADVER`: the session's release; `dwg_format` is unavailable over COM), `insunits` + `insunits_name`, `measurement` + `measurement_name` (`imperial`/`metric`), `spaces` (`layout`, `is_model`, `block`) |
| `layouts` | per layout, model first then tab order: `name`, `is_model`, `tab_order`, `block`, `entity_count`, `viewports` |
| `entities` | every entity of model space and of every paper space, in that order |
| `blocks` | `{name: definition}` for each block referenced by an insert, followed to `block_depth` |
| `blocks_not_read` | `{block, depth, reason}` for definitions beyond `block_depth` |
| `counts` | `by_type: {ObjectName: {read, skipped, failed, with_errors}}`, `skipped_reasons: {ObjectName: reason}`, `total` |
| `warnings` | e.g. a space whose entity count changed during the export |

## Every entity

`type`, `object_name` (AutoCAD's class, e.g. `AcDbRotatedDimension`), `handle`, `layer`, and its owner: `space`
(`model` or `paper`) and `layout`; inside a block definition, `space: "block"` and `block`.
A type with no reader has `type: "other"` and `skipped: <reason>`; an entity that could not be read at all has
`type: "unreadable"` and `failed`.

| `type` | Fields |
|---|---|
| `line` | `start`, `end` |
| `polyline` (LWPOLYLINE) | `vertices` `[[x, y]]`, `bulges` (one per vertex), `closed`, `elevation` |
| `polyline2d` | `vertices` `[[x, y, z]]`, `bulges`, `closed`, `fit_type` |
| `polyline3d` | `vertices`, `closed` |
| `arc`, `circle` | `center`, `radius`, (`start_angle`, `end_angle`), `normal` |
| `ellipse` | `center`, `major_axis`, `radius_ratio`, `start_angle`, `end_angle`, `normal` |
| `spline` | `degree`, `closed`, `rational`, `control_points`, `knots`, `weights` (null unless rational), `fit_point_count`, `fit_points` |
| `point`, `xline`, `ray` | `position`; `base_point`, `direction` |
| `text` | `raw` (with `%%` codes), `plain`, `position`, `height`, `rotation`, `style`, `alignment`, `alignment_point` |
| `mtext` | `raw` (with formatting codes), `plain`, `position`, `height`, `rotation`, `style`, `width`, `attachment` |
| `leader` | `points`, `leader_type`, `annotation_handle`, `raw`, `plain` (the MText it carries) |
| `multileader` | `content_type`, `raw`, `plain` (MText content) or `content_block`, `leader_lines` `[[point]]` |
| `dimension` | below |
| `insert` | `name`, `effective_name` (dynamic blocks), `position`, `scale` `[x, y, z]`, `rotation`, `normal`, `attributes` `[{tag, value}]`; MINSERT adds `rows`, `columns`, `row_spacing`, `column_spacing` |
| `attribute_definition` | `tag`, `prompt`, `default`, `position`, `height`, `rotation`, `constant` |
| `table` | `rows`, `columns`, `cells` (text, row by row) |
| `viewport` | `center`, `width`, `height` (on the sheet), `target`, `direction`, `custom_scale`, `standard_scale`, `twist_angle`; `view_center` and `frozen_layers` null and unavailable. Also copied into its layout's `viewports` |

Skipped with a reason: hatches, 2D solids, traces, 3D faces, ACIS solids, regions and bodies, meshes, images,
wipeouts, OLE, multilines, tolerance frames, proxies, Civil 3D (`Aecc*`) and Architecture (`Aec*`) objects, and any
other class.

## Dimensions

| Field | Content |
|---|---|
| `dim_type` | `rotated` (horizontal, vertical, rotated: the linear ones), `aligned`, `angular` (2-line and 3-point), `radial`, `diametric`, `ordinate`, `arc_length`, `radial_large` (jogged) |
| `measurement` | AutoCAD's `Measurement` (radians for angular) |
| `text_override` | `TextOverride`, raw |
| `displayed_text` | the override with `<>` replaced by the formatted measurement (and `[]` by the alternate units), or the formatted measurement when there is no override; a single-space override shows nothing; MText codes kept |
| `displayed_text_plain` | the same, formatting stripped (`%%c` → Ø, `\P` → new line) |
| `displayed_text_source` | `"computed"`: ActiveX has no rendered-text property |
| `displayed_text_approximate` | true for architectural, fractional, engineering or Windows units, DMS, arc symbols, tolerances, or alternate units after a free-text override |
| `formatted_measurement` | what `<>` stands for: prefix (or the automatic `R` / `%%c`), number, suffix, tolerance |
| `text_position`, `text_rotation`, `rotation` (rotated) | |
| `points` | what the interface exposes: `ext_line1_point`, `ext_line2_point` (aligned, arc), the four `ext_line*_start/end_point` (2-line angular), `angle_vertex` (3-point), `arc_point`, `center_point`, `leader1/2_point` (arc), `center_point`, `chord_point`, `override_center`, `jog_location` (jogged) |
| `unavailable` | always `dimension_line_points`; rotated `ext_line1_point`, `ext_line2_point` (not in AutoCAD 2025's `IAcadDimRotated`); radial `center_point`, `chord_point`; diametric `chord_point`, `far_chord_point`; ordinate `feature_point`, `leader_end_point` |
| `style` | `name`, and the dimension's **effective** settings (its style plus overrides): `units_format`, `precision`, `linear_scale_factor`, `round_distance`, `suppress_zero_feet`, `suppress_zero_inches` (or `angle_format`, `precision` for angular), `suppress_leading_zeros`, `suppress_trailing_zeros`, `decimal_separator`, `prefix`, `suffix`, `tolerance_display` (+ limits and precision), `alt_units` (null or `{units_format, units_format_com, precision, scale, round_distance, suppress_*, prefix, suffix}`) |

`AcadDimStyle` has no getters over COM, so the style's own table values are not exported; each dimension's
effective values are what it shows.

### The displayed-text rule (`export_text.displayed_text`)

- Linear value = `Measurement × LinearScaleFactor`, rounded to `RoundDistance` if set, then to `precision` places
  half away from zero; trailing zeros dropped when suppressed (`12.50` → `12.5`, `12.00` → `12`), the leading zero
  when suppressed (`0.50` → `.50`); `DecimalSeparator` applied.
- Scientific `1.50E+03`; engineering `1'-6.5"`; architectural `1'-6 1/2"` (denominator 2^precision); fractional
  `6 1/2`. Feet and inches follow `SuppressZeroFeet` (`6 1/2"`, `1/2"`) and `SuppressZeroInches` (`6'`).
- Angular: degrees `45°`, DMS `45°30'` (precision 1–2: minutes; 3–4: seconds), grads `g`, radians `r`.
- Prefix replaces the automatic `R` (radial) or `Ø` (diametric); the arc-length symbol `⌒` precedes when
  `SymbolPosition` is 0.
- Alternate units: `[alt]` after the primary text, `Measurement × LinearScaleFactor × AltUnitsScale`, in their own
  format.
