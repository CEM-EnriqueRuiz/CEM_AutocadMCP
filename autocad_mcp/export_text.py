"""Cemengal: the text rules of export_drawing (docs/decisions/0006, docs/concepts/export-schema.md).

Pure functions, no COM: the plain text of TEXT and MTEXT, and the text a dimension displays. ActiveX has no
"rendered text" property for a dimension, so the displayed text is computed from the dimension's own effective
format settings: the override with "<>" replaced by the formatted measurement, or the formatted measurement when
there is no override. Decimal, scientific, grads and radians are exact; architectural, fractional, engineering,
Windows-desktop units, degrees-minutes-seconds, arc-length symbols and tolerances are flagged approximate.
"""
import math
import re
from decimal import ROUND_HALF_UP, Decimal

# AcDimLUnits (UnitsFormat): 1 scientific, 2 decimal, 3 engineering, 4 architectural, 5 fractional, 6 Windows
SCIENTIFIC, DECIMAL, ENGINEERING, ARCHITECTURAL, FRACTIONAL, WINDOWS = 1, 2, 3, 4, 5, 6
# AcDimUnits (AltUnitsFormat) numbers the same formats differently; stacked and unstacked map to one
ALT_TO_LINEAR = {1: SCIENTIFIC, 2: DECIMAL, 3: ENGINEERING, 4: ARCHITECTURAL, 5: FRACTIONAL,
                 6: ARCHITECTURAL, 7: FRACTIONAL, 8: WINDOWS}
# AcAngleUnits (AngleFormat): 0 decimal degrees, 1 degrees-minutes-seconds, 2 grads, 3 radians
DEGREES, DMS, GRADS, RADIANS = 0, 1, 2, 3
ANGULAR = {"angular"}
SYMBOLS = {"radial": "R", "radial_large": "R", "diametric": "%%c"}

_CODES = {"d": "°", "p": "±", "c": "Ø", "%": "%"}
_PERCENT = re.compile(r"%%(\d{3}|[dpcuok%])", re.IGNORECASE)


def text_plain(raw):
    """TEXT: %%d, %%p, %%c and %%nnn become their characters; %%u, %%o, %%k (underline, overline, strike) go."""
    if raw is None:
        return None

    def code(match):
        token = match.group(1).lower()
        if token.isdigit():
            return chr(int(token))
        return _CODES.get(token, "")

    return _PERCENT.sub(code, raw)


def mtext_plain(raw):
    """MTEXT: formatting codes stripped, \\P and \\X as new lines, stacks as a/b, escapes kept literally."""
    if raw is None:
        return None
    out, i, n = [], 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "\\" and i + 1 < n:
            k = raw[i + 1]
            if k in "\\{}":
                out.append(k)
                i += 2
            elif k in "PX":
                out.append("\n")
                i += 2
            elif k == "~":
                out.append(" ")
                i += 2
            elif k == "U" and raw[i + 2:i + 3] == "+" and re.fullmatch(r"[0-9A-Fa-f]{4}", raw[i + 3:i + 7] or ""):
                out.append(chr(int(raw[i + 3:i + 7], 16)))
                i += 7
            elif k == "S":
                end = raw.find(";", i + 2)
                end = n if end < 0 else end
                out.append(re.sub(r"[\^#]", "/", raw[i + 2:end]).strip())
                i = end + 1
            elif k in "fFHCcTQWAp":
                end = raw.find(";", i + 2)
                i = n if end < 0 else end + 1
            elif k in "LlOoKkN":
                i += 2
            else:
                out.append(k)
                i += 2
        elif c in "{}":
            i += 1
        else:
            out.append(c)
            i += 1
    return text_plain("".join(out))


# --- numbers --------------------------------------------------------------------------------------------------

def _dec(value):
    return Decimal(repr(float(value)))


def _round_to(value, step):
    if not step:
        return _dec(value)
    step = _dec(step)
    return (_dec(value) / step).quantize(Decimal(1), ROUND_HALF_UP) * step


def format_decimal(value, precision, suppress_leading=False, suppress_trailing=False, separator="."):
    """AutoCAD's decimal rule: round half away from zero to `precision` places, then the zero suppressions."""
    precision = max(0, int(precision or 0))
    d = (value if isinstance(value, Decimal) else _dec(value)).quantize(Decimal(1).scaleb(-precision), ROUND_HALF_UP)
    s = f"{d:f}"
    if s.startswith("-") and not d:
        s = s[1:]
    if suppress_trailing and "." in s:
        s = s.rstrip("0").rstrip(".")
    if suppress_leading:
        if s.startswith("0.") and len(s) > 2:
            s = s[1:]
        elif s.startswith("-0.") and len(s) > 3:
            s = "-" + s[2:]
    return s.replace(".", separator or ".")


def _fraction(value, precision):
    den = 2 ** max(0, int(precision or 0))
    n = int((_dec(value) * den).quantize(Decimal(1), ROUND_HALF_UP))
    return n, den


def _reduced(num, den):
    g = math.gcd(num, den)
    return num // g, den // g


def _format_fractional(value, precision):
    n, den = _fraction(value, precision)
    whole, rest = divmod(n, den)
    if not rest:
        return str(whole)
    num, den = _reduced(rest, den)
    return f"{whole} {num}/{den}" if whole else f"{num}/{den}"


def _feet_inches(feet, inches, zero, zero_feet, zero_inches):
    """AutoCAD's DIMZIN for feet-and-inches: zero feet dropped (6 1/2"), zero inches dropped (6')."""
    if feet == 0 and zero_feet and not zero:
        return f'{inches}"'
    if zero and zero_inches and feet:
        return f"{feet}'"
    return f"{feet}'-{inches}\""


def _format_architectural(value, precision, zero_feet=False, zero_inches=False):
    n, den = _fraction(value, precision)
    feet, rest = divmod(n, 12 * den)
    whole, frac = divmod(rest, den)
    inches = str(whole)
    if frac:
        num, d = _reduced(frac, den)
        inches = f"{num}/{d}" if whole == 0 and feet == 0 and zero_feet else f"{whole} {num}/{d}"
    return _feet_inches(feet, inches, rest == 0, zero_feet, zero_inches)


def format_linear(value, units_format, precision, suppress_leading=False, suppress_trailing=False, separator=".",
                  zero_feet=False, zero_inches=False):
    """A length in the dimension's units format; returns (text, approximate)."""
    units_format = int(units_format or DECIMAL)
    if units_format == SCIENTIFIC:
        return f"{float(value):.{max(0, int(precision or 0))}E}".replace(".", separator or "."), False
    if units_format == ENGINEERING:
        feet = int(float(value) // 12)
        rest = float(value) - 12 * feet
        inches = format_decimal(rest, precision, False, suppress_trailing, separator)
        return _feet_inches(feet, inches, not float(_dec(rest).quantize(Decimal(1).scaleb(-max(0, int(precision or 0))),
                                                                        ROUND_HALF_UP)), zero_feet, zero_inches), True
    if units_format == ARCHITECTURAL:
        return _format_architectural(value, precision, zero_feet, zero_inches), True
    if units_format == FRACTIONAL:
        return _format_fractional(value, precision), True
    return format_decimal(value, precision, suppress_leading, suppress_trailing, separator), units_format == WINDOWS


def format_angle(radians, angle_format, precision, suppress_leading=False, suppress_trailing=False, separator="."):
    """An angle (COM gives radians) in the dimension's angle format; returns (raw text, approximate)."""
    angle_format = int(angle_format or DEGREES)
    precision = max(0, int(precision or 0))
    if angle_format == GRADS:
        return format_decimal(radians * 200 / math.pi, precision, suppress_leading, suppress_trailing,
                              separator) + "g", False
    if angle_format == RADIANS:
        return format_decimal(radians, precision, suppress_leading, suppress_trailing, separator) + "r", False
    degrees = math.degrees(radians)
    if angle_format == DMS:
        seconds = _dec(degrees) * 3600
        if precision == 0:
            d = int((seconds / 3600).quantize(Decimal(1), ROUND_HALF_UP))
            return f"{d}%%d", True
        if precision <= 2:
            minutes = int((seconds / 60).quantize(Decimal(1), ROUND_HALF_UP))
            d, m = divmod(minutes, 60)
            return f"{d}%%d{m}'", True
        places = max(0, precision - 4)
        total = seconds.quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)
        d, rest = divmod(total, 3600)
        m, s = divmod(rest, 60)
        return f"{int(d)}%%d{int(m)}'{format_decimal(s, places, False, suppress_trailing, separator)}\"", True
    return format_decimal(degrees, precision, suppress_leading, suppress_trailing, separator) + "%%d", False


# --- the displayed text ---------------------------------------------------------------------------------------

def _primary(dim_type, measurement, fmt):
    """The text "<>" stands for: prefix (or the automatic R / Ø), the formatted number, suffix, tolerance."""
    lead = fmt.get("suppress_leading_zeros", False)
    trail = fmt.get("suppress_trailing_zeros", False)
    sep = fmt.get("decimal_separator") or "."
    if dim_type in ANGULAR:
        number, approximate = format_angle(measurement, fmt.get("angle_format"), fmt.get("precision"), lead, trail,
                                           sep)
        value = None
    else:
        value = _round_to(float(measurement) * float(fmt.get("linear_scale_factor") or 1.0),
                          fmt.get("round_distance") or 0.0)
        number, approximate = format_linear(value, fmt.get("units_format"), fmt.get("precision"), lead, trail, sep,
                                            fmt.get("suppress_zero_feet", False), fmt.get("suppress_zero_inches", False))
    prefix = fmt.get("prefix") or ""
    if not prefix:
        prefix = SYMBOLS.get(dim_type, "")
        if dim_type == "arc_length" and int(fmt.get("symbol_position") or 0) == 0:
            prefix, approximate = "⌒", True
    text = prefix + number + (fmt.get("suffix") or "")
    tolerance = int(fmt.get("tolerance_display") or 0)
    if tolerance and value is not None:
        tp = fmt.get("tolerance_precision", fmt.get("precision"))
        upper = float(fmt.get("tolerance_upper") or 0.0)
        lower = float(fmt.get("tolerance_lower") or 0.0)
        tol = lambda v: format_decimal(v, tp, lead, trail, sep)
        if tolerance == 1:  # symmetrical
            text += "%%p" + tol(upper)
        elif tolerance == 2:  # deviation
            text += f" +{tol(upper)}/-{tol(lower)}"
        elif tolerance == 3:  # limits
            text = prefix + tol(float(value) + upper) + "/" + tol(float(value) - lower) + (fmt.get("suffix") or "")
        approximate = True
    return text, approximate


def _alternate(measurement, fmt):
    alt = fmt.get("alt_units")
    if not alt or measurement is None:
        return None, False
    value = _round_to(float(measurement) * float(fmt.get("linear_scale_factor") or 1.0) * float(alt.get("scale") or 1.0),
                      alt.get("round_distance") or 0.0)
    number, approximate = format_linear(value, alt.get("units_format"), alt.get("precision"),
                                        alt.get("suppress_leading_zeros", False),
                                        alt.get("suppress_trailing_zeros", False), fmt.get("decimal_separator") or ".",
                                        alt.get("suppress_zero_feet", False), alt.get("suppress_zero_inches", False))
    return "[" + (alt.get("prefix") or "") + number + (alt.get("suffix") or "") + "]", approximate


def displayed_text(dim_type, measurement, override, fmt):
    """What the dimension shows: {"text" (raw, MText codes kept), "plain", "source", "approximate",
    "formatted_measurement" (what "<>" stands for)}. A text that cannot be known is None."""
    override = override or ""
    primary, approximate = (None, False) if measurement is None else _primary(dim_type, measurement, fmt)
    alt, alt_approximate = _alternate(measurement, fmt) if dim_type not in ANGULAR else (None, False)
    approximate = approximate or alt_approximate
    if override and not override.strip():
        text = ""  # a single space suppresses the text
    elif not override or "<>" in override:
        if primary is None:
            text = None
        else:
            text = override.replace("<>", primary) if override else primary
            if alt is not None:
                if "[]" in text:
                    text = text.replace("[]", alt)
                else:
                    approximate = approximate or bool(override)
                    text += " " + alt
    else:
        text = override.replace("[]", alt) if alt is not None else override  # the written text prevails
    return {"text": text, "plain": mtext_plain(text), "source": "computed", "approximate": approximate,
            "formatted_measurement": primary}
