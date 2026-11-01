"""Canonical schema, column detection, and value-normalization helpers.

The IMD "Best Track" workbook is human-maintained, so column *headers* drift
between years (typos, abbreviations, re-orderings, split date columns).  Rather
than rely on fixed positions we detect each field by keyword-matching the header
text.  Everything a downstream module needs to know about the raw layout lives
here.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Optional

# Canonical field names, in the order we want them to appear in the DataFrame.
FIELDS = [
    "serial",
    "basin",
    "name",
    "date",
    "time",
    "lat",
    "lon",
    "ci_no",
    "pressure",
    "wind",
    "pressure_drop",
    "grade",
    "oci",
    "oci_diameter",
]

# Human-readable descriptions / units, surfaced as xarray attrs.
FIELD_ATTRS = {
    "serial": {"long_name": "Serial number of system during the year"},
    "basin": {"long_name": "Basin of origin (BOB=Bay of Bengal, ARB=Arabian Sea, LAND)"},
    "name": {"long_name": "Cyclone name (blank when unnamed)"},
    "time": {"long_name": "Observation time", "timezone": "UTC"},
    "lat": {"long_name": "Latitude", "units": "degrees_north"},
    "lon": {"long_name": "Longitude", "units": "degrees_east"},
    "ci_no": {"long_name": "Dvorak CI number (a.k.a. T number)"},
    "pressure": {"long_name": "Estimated central pressure", "units": "hPa"},
    "wind": {"long_name": "Maximum sustained surface wind", "units": "knots"},
    "pressure_drop": {"long_name": "Pressure drop (delta P)", "units": "hPa"},
    "grade": {"long_name": "Intensity grade (text)"},
    "oci": {"long_name": "Pressure of outermost closed isobar", "units": "hPa"},
    "oci_diameter": {"long_name": "Diameter of outermost closed isobar", "units": "degrees"},
}

# Which canonical fields are numeric (float) vs text.
NUMERIC_FIELDS = {"lat", "lon", "ci_no", "pressure", "wind", "pressure_drop", "oci", "oci_diameter"}

# Canonical basin codes.  "AS" (Arabian Sea) is a newer abbreviation for ARB.
_BASIN_MAP = {
    "BOB": "BOB",
    "ARB": "ARB",
    "AS": "ARB",
    "LAND": "LAND",
}
VALID_BASINS = set(_BASIN_MAP)

# Canonical IMD intensity grades.  Anything that maps to None is treated as a
# non-track (remark) marker or missing.
_GRADE_MAP = {
    "D": "D",  # Depression
    "DD": "DD",  # Deep Depression
    "CS": "CS",  # Cyclonic Storm
    "SCS": "SCS",  # Severe Cyclonic Storm
    "VSCS": "VSCS",  # Very Severe Cyclonic Storm
    "ESCS": "ESCS",  # Extremely Severe Cyclonic Storm
    "SUCS": "SuCS",  # Super Cyclonic Storm
}
GRADE_ORDER = ["D", "DD", "CS", "SCS", "VSCS", "ESCS", "SuCS"]

GRADE_LONG = {
    "D": "Depression",
    "DD": "Deep Depression",
    "CS": "Cyclonic Storm",
    "SCS": "Severe Cyclonic Storm",
    "VSCS": "Very Severe Cyclonic Storm",
    "ESCS": "Extremely Severe Cyclonic Storm",
    "SuCS": "Super Cyclonic Storm",
}


def detect_columns(header_cells) -> dict[str, int]:
    """Map canonical field name -> column index, from a header row.

    Matching is keyword based and order-sensitive (more specific keywords are
    tested first) so it survives the many header spellings seen across years.
    """
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(header_cells):
        if cell is None:
            continue
        h = str(cell).strip().lower()
        if not h:
            continue
        if "serial" in h:
            field = "serial"
        elif "basin" in h or "barbin" in h:
            field = "basin"
        elif h == "name" or h.startswith("name"):
            field = "name"
        elif "date" in h:
            field = "date"
        elif "time" in h:
            field = "time"
        elif "lat" in h:
            field = "lat"
        elif "long" in h or "lon" in h:
            field = "lon"
        elif "ci no" in h or "t. no" in h or "t.no" in h or h.startswith("ci"):
            field = "ci_no"
        elif "drop" in h or "delta" in h:
            field = "pressure_drop"
        elif "central pressure" in h or "e.c.p" in h or "ecp" in h:
            field = "pressure"
        elif "wind" in h:
            field = "wind"
        elif "diameter" in h or "size of outermost" in h:
            field = "oci_diameter"
        elif "isobar" in h:
            field = "oci"
        elif "grade" in h:
            field = "grade"
        else:
            # Redundant split-date columns (DD/MM/YYYY) and anything else.
            continue
        # First occurrence wins; ignore duplicate/split columns.
        mapping.setdefault(field, idx)
    return mapping


def is_header_row(cells) -> bool:
    return any(c is not None and "serial" in str(c).strip().lower() for c in cells)


def to_float(value) -> float:
    """Coerce a messy cell to float, returning NaN for missing/sentinel values."""
    if value is None:
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s in ("", "-", "--", "N", "NA", "NaN", "nan"):
        return math.nan
    # Keep only leading numeric portion (handles stray units / spaces).
    m = re.match(r"[-+]?\d*\.?\d+", s)
    return float(m.group()) if m else math.nan


def parse_latlon(lat_raw, lon_raw) -> tuple[float, float]:
    """Return ``(lat, lon)`` as floats, handling the packed ``"lat/lon"`` form.

    Some rows (e.g. 2013 LEHAR/MADI) pack both coordinates into a single string
    like ``"8.5/96.5"`` — and put it in *both* the latitude and longitude cells.
    Naively taking the leading number gives ``lon == lat``. Detect the pair and
    split it; otherwise coerce each cell independently.
    """
    for cell in (lat_raw, lon_raw):
        if isinstance(cell, str) and "/" in cell:
            parts = cell.split("/")
            if len(parts) == 2:
                a, b = to_float(parts[0]), to_float(parts[1])
                if a == a and b == b:  # both parsed (not NaN)
                    return a, b
    return to_float(lat_raw), to_float(lon_raw)


def parse_date(value) -> Optional[datetime]:
    """Parse a Date cell to a ``datetime`` (date part only), or None.

    The workbook stores the date inconsistently: usually a real ``datetime``,
    but sometimes a day-first text string (``"16-06-2008"``, ``"01/10/2025"``).
    Both must be understood, or every fix in a text-dated storm gets dropped.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    # Day-first DD-MM-YYYY / DD/MM/YYYY / DD.MM.YYYY (IMD convention).
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if not m:
        return None
    day, month, year = (int(g) for g in m.groups())
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def parse_time(value) -> Optional[int]:
    """Parse a Time (UTC) cell into minutes-since-midnight, or None if not a time.

    Track rows use HHMM (e.g. '0300', 300, '0', 2100).  Remark rows carry free
    text here instead, for which we return None.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, datetime):
        return value.hour * 60 + value.minute
    s = str(value).strip()
    if not re.fullmatch(r"\d{1,4}", s):
        return None
    hhmm = int(s)
    hh, mm = divmod(hhmm, 100)
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


def normalize_basin(value) -> Optional[str]:
    if value is None:
        return None
    return _BASIN_MAP.get(str(value).strip().upper())


def normalize_grade(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    if not s:
        return None
    # Collapse things like "D OVER LAND" -> "D".
    token = re.split(r"[\s/]", s, maxsplit=1)[0]
    return _GRADE_MAP.get(token)


def normalize_name(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    # Strip stray quotes / apostrophes (incl. curly) that cling to some names.
    s = s.strip("'\"‘’“” ").strip()
    # Dash-only cells are "unnamed" placeholders, not names.
    if not s or set(s) <= {"-", "–", "—"}:
        return None
    # Reject remark text that spilled into the name column: real cyclone names
    # are short alphabetic tokens (occasionally two words), never sentences.
    if len(s) > 20 or any(ch.isdigit() for ch in s) or s.count(" ") > 1:
        return None
    if not all(ch.isalpha() or ch in " -" for ch in s):
        return None
    return s
