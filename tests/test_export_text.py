"""docs/decisions/0006 and docs/concepts/export-schema.md: the plain text of TEXT and MTEXT, and the displayed text
of a dimension (the written text prevails in the modelling standard, so this rule is the core of the export)."""
import math

import pytest

from autocad_mcp.export_text import displayed_text, mtext_plain, text_plain


# --- TEXT and MTEXT --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw, plain", [
    ("%%c50 %%p0.1 90%%d", "Ø50 ±0.1 90°"),
    ("%%uUnder%%u and %%oover%%o", "Under and over"),
    ("100%%%", "100%"),
    ("%%065", "A"),
    ("plain", "plain"),
])
def test_text_control_codes_become_plain_text(raw, plain):
    assert text_plain(raw) == plain


@pytest.mark.parametrize("raw, plain", [
    (r"{\fArial|b0|i0|c0|p34;\H2.5;Vista A}\PLine 2", "Vista A\nLine 2"),
    (r"\C1;red \c255;true", "red true"),
    (r"\LUnder\l \OOver\o \KStrike\k", "Under Over Strike"),
    (r"\S+0.1^-0.2;", "+0.1/-0.2"),
    (r"\S1#2;", "1/2"),
    (r"a\\b \{x\}", r"a\b {x}"),
    (r"\U+00D8" + "50", "Ø50"),
    (r"A\~B", "A B"),
    (r"\A1;\T1.1;\Q15;\W0.8;tracked", "tracked"),
    (r"\pxi-3,l3;Item", "Item"),
    ("%%c20", "Ø20"),
    (r"1500\XVista Z", "1500\nVista Z"),
])
def test_mtext_formatting_is_stripped(raw, plain):
    assert mtext_plain(raw) == plain


# --- the displayed text of a dimension -------------------------------------------------------------------------

def linear(**fmt):
    base = {"units_format": 2, "precision": 0, "linear_scale_factor": 1.0, "round_distance": 0.0,
            "suppress_leading_zeros": False, "suppress_trailing_zeros": False, "decimal_separator": ".",
            "prefix": "", "suffix": "", "alt_units": None, "tolerance_display": 0}
    base.update(fmt)
    return base


def test_without_override_the_formatted_measurement_is_displayed():
    shown = displayed_text("rotated", 1499.99999, "", linear())
    assert shown == {"text": "1500", "plain": "1500", "source": "computed", "approximate": False,
                     "formatted_measurement": "1500"}


@pytest.mark.parametrize("value, fmt, text", [
    (12.5, dict(precision=2), "12.50"),
    (12.5, dict(precision=2, suppress_trailing_zeros=True), "12.5"),
    (12.0, dict(precision=2, suppress_trailing_zeros=True), "12"),
    (0.5, dict(precision=2, suppress_leading_zeros=True), ".50"),
    (12.5, dict(precision=2, decimal_separator=","), "12,50"),
    (2.5, dict(precision=2, linear_scale_factor=10.0), "25.00"),
    (1503, dict(round_distance=5.0), "1505"),
    (1502, dict(round_distance=5.0), "1500"),
    (2.25, dict(precision=1), "2.3"),
    (1500, dict(prefix="L=", suffix=" mm"), "L=1500 mm"),
    (1500.0, dict(units_format=1, precision=2), "1.50E+03"),
])
def test_decimal_formatting_follows_the_dimension_settings(value, fmt, text):
    shown = displayed_text("aligned", value, "", linear(**fmt))
    assert shown["text"] == text and shown["approximate"] is False


@pytest.mark.parametrize("override, text, plain", [
    ("<> TYP.", "1500 TYP.", "1500 TYP."),
    ("2X <>", "2X 1500", "2X 1500"),
    ("1600", "1600", "1600"),  # the written override prevails over the measurement
    (r"<>\PVista A", r"1500\PVista A", "1500\nVista A"),
    (" ", "", ""),  # a single space suppresses the text
])
def test_an_override_replaces_or_wraps_the_measurement(override, text, plain):
    shown = displayed_text("rotated", 1500.0, override, linear())
    assert (shown["text"], shown["plain"]) == (text, plain)
    assert shown["formatted_measurement"] == "1500"


def test_radial_and_diametric_get_their_symbol_unless_a_prefix_is_set():
    assert displayed_text("radial", 25.0, "", linear())["plain"] == "R25"
    assert displayed_text("radial", 25.0, "", linear(prefix="R="))["plain"] == "R=25"
    shown = displayed_text("diametric", 50.0, "", linear())
    assert shown["text"] == "%%c50" and shown["plain"] == "Ø50"
    assert displayed_text("diametric", 50.0, "<> H7", linear())["plain"] == "Ø50 H7"


def angular(**fmt):
    base = {"angle_format": 0, "precision": 0, "suppress_leading_zeros": False, "suppress_trailing_zeros": False,
            "decimal_separator": ".", "prefix": "", "suffix": "", "tolerance_display": 0}
    base.update(fmt)
    return base


def test_angular_dimensions_are_shown_in_degrees():
    assert displayed_text("angular", math.pi / 2, "", angular())["plain"] == "90°"
    assert displayed_text("angular", math.radians(45.5), "", angular(precision=1))["plain"] == "45.5°"
    assert displayed_text("angular", math.pi / 2, "", angular(precision=2, suppress_trailing_zeros=True))[
        "plain"] == "90°"


def test_degrees_minutes_seconds_are_flagged_approximate():
    shown = displayed_text("angular", math.radians(45.5), "", angular(angle_format=1, precision=2))
    assert shown["plain"] == "45°30'" and shown["approximate"] is True


def test_alternate_units_follow_in_brackets():
    alt = {"units_format": 2, "precision": 2, "scale": 1 / 25.4, "round_distance": 0.0,
           "suppress_leading_zeros": False, "suppress_trailing_zeros": False, "prefix": "", "suffix": ""}
    shown = displayed_text("rotated", 25.4, "", linear(precision=1, alt_units=alt))
    assert shown["plain"] == "25.4 [1.00]" and shown["approximate"] is False
    assert displayed_text("rotated", 25.4, "<> [] TYP", linear(precision=1, alt_units=alt))["plain"] == \
        "25.4 [1.00] TYP"


@pytest.mark.parametrize("value, fmt, text", [
    (18.5, dict(units_format=4, precision=4), "1'-6 1/2\""),
    (6.5, dict(units_format=5, precision=3), "6 1/2"),
    (18.5, dict(units_format=3, precision=1), "1'-6.5\""),
])
def test_architectural_fractional_and_engineering_are_flagged_approximate(value, fmt, text):
    shown = displayed_text("rotated", value, "", linear(**fmt))
    assert shown["text"] == text and shown["approximate"] is True


@pytest.mark.parametrize("value, fmt, text", [
    # live 2026-11-01: 1,541 of 2,945 architectural dimensions were under a foot, 407 whole feet
    (6.5, dict(suppress_zero_feet=True), "6 1/2\""),
    (6.5, dict(suppress_zero_feet=False), "0'-6 1/2\""),
    (72.0, dict(suppress_zero_inches=True), "6'"),
    (72.0, dict(suppress_zero_inches=False), "6'-0\""),
    (12.5, dict(suppress_zero_inches=True), "1'-0 1/2\""),
    (0.5, dict(suppress_zero_feet=True, suppress_zero_inches=True), "1/2\""),
])
def test_architectural_zero_feet_and_zero_inches_follow_the_suppression(value, fmt, text):
    shown = displayed_text("rotated", value, "", linear(units_format=4, precision=4, **fmt))
    assert shown["text"] == text and shown["approximate"] is True


def test_engineering_zero_feet_and_zero_inches_follow_the_suppression():
    assert displayed_text("rotated", 6.5, "", linear(units_format=3, precision=1, suppress_zero_feet=True))[
        "text"] == "6.5\""
    assert displayed_text("rotated", 72.0, "", linear(units_format=3, precision=1, suppress_zero_inches=True))[
        "text"] == "6'"


def test_tolerances_are_appended_and_flagged_approximate():
    shown = displayed_text("rotated", 1500.0, "", linear(tolerance_display=1, tolerance_upper=0.5,
                                                         tolerance_lower=0.5, tolerance_precision=1))
    assert shown["plain"] == "1500±0.5" and shown["approximate"] is True


def test_a_missing_measurement_gives_no_text_but_an_override_still_shows():
    assert displayed_text("rotated", None, "", linear())["text"] is None
    assert displayed_text("rotated", None, "1600", linear())["text"] == "1600"
    assert displayed_text("rotated", None, "<>", linear())["text"] is None
