"""Parse the IMD Best Track workbook into tidy pandas structures.

The workbook has one sheet per year.  Each sheet contains several storms, one
after another; a storm's ``serial`` number appears only on its first row, and
free-text landfall / weakening notes are interleaved between the 3-hourly track
rows.  :func:`parse_workbook` untangles all of that into two frames:

* ``observations`` - one tidy row per 3-hourly fix (the "track").
* ``remarks``      - the free-text notes, linked back to their storm.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Union

import pandas as pd

from . import _schema as S

PathLike = Union[str, Path]


def _iter_year_sheets(wb):
    for name in wb.sheetnames:
        name_s = str(name).strip()
        if name_s.isdigit() and 1800 < int(name_s) < 2200:
            yield int(name_s), wb[name]


def _remark_text(row) -> str:
    """Join the long free-text fragments of a non-track row into one string."""
    parts = []
    for cell in row:
        if cell is None:
            continue
        s = str(cell).strip()
        if len(s) > 12 and any(ch.isalpha() for ch in s):
            parts.append(s)
    return " ".join(parts)


def _serial_of(row, get) -> Union[int, None]:
    raw = get(row, "serial")
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _serial_run(rows, start: int, serial: int, get) -> tuple[int, Union[int, None]]:
    """How many rows the serial at ``rows[start]`` covers, and what follows it.

    Rows with an empty serial cell continue the current storm (the column is
    merged in many sheets), so the run ends at the next row carrying a
    *different* explicit serial. Returns ``(run_length, next_serial)``.
    """
    run = 0
    for j in range(start, len(rows)):
        if not any(c is not None for c in rows[j]):
            break
        sv = _serial_of(rows[j], get)
        if sv is None or sv == serial:
            run += 1
        else:
            return run, sv
    return run, None


def parse_sheet(year: int, ws) -> tuple[list[dict], list[dict]]:
    # Materialised because the storm-boundary rules need one row of lookahead.
    all_rows = list(ws.iter_rows(values_only=True))

    # Locate the header row (it may be preceded by note rows).
    colmap = None
    header_at = None
    for i, row in enumerate(all_rows):
        if S.is_header_row(row):
            colmap = S.detect_columns(row)
            header_at = i
            break
    if colmap is None:
        return [], []
    rows = all_rows[header_at + 1 :]

    def get(row, field):
        idx = colmap.get(field)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    observations: list[dict] = []
    remarks: list[dict] = []

    cur_serial = None
    cur_basin = None
    cur_name = None
    cur_date = None
    storm_no = 0
    separator_seen = True  # start of sheet counts as a storm boundary

    for i, row in enumerate(rows):
        if not any(c is not None for c in row):
            separator_seen = True  # blank rows usually separate storms
            continue

        serial_val = _serial_of(row, get)
        row_basin = S.normalize_basin(get(row, "basin"))

        # Deciding where one storm ends and the next begins.
        #
        # A storm is keyed by (serial, basin): IMD restarts the serial per basin
        # in older years, so ARB #1 following BOB #1 is a new storm even though
        # the serial is unchanged. Two workbook quirks have to be tolerated:
        #
        #  * a stray blank row *inside* a block (2001 serial 2) — a separator
        #    alone must not open a new storm if the key is unchanged;
        #  * a single-row serial typo (2005 FANOOS is numbered 10 on one row of
        #    an otherwise 11 block) — a serial that covers one row and then
        #    reverts is an error, not a boundary.
        new_storm = False
        if serial_val is not None:
            if cur_serial is None:
                new_storm = True
            elif serial_val != cur_serial:
                # A typo covers a single row *inside* a block and then reverts;
                # a real boundary either follows a separator or changes basin
                # (both of which happen between one-row storms in older sheets).
                run, next_serial = _serial_run(rows, i, serial_val, get)
                typo = (
                    run == 1
                    and next_serial == cur_serial
                    and not separator_seen
                    and (row_basin is None or row_basin == cur_basin)
                )
                if typo:
                    serial_val = cur_serial  # keep the row in the current storm
                else:
                    new_storm = True
            elif separator_seen and row_basin is not None and row_basin != cur_basin:
                new_storm = True

        if new_storm:
            storm_no += 1
            cur_serial = serial_val
            cur_name = None  # don't let the previous storm's fields forward-fill in
            cur_basin = None
            cur_date = None
        elif serial_val is not None:
            cur_serial = serial_val
        separator_seen = False

        basin = row_basin
        if basin is not None:
            cur_basin = basin
        name = S.normalize_name(get(row, "name"))
        if name is not None:
            cur_name = name

        # The Date column is a *merged* cell in the workbook: it holds the date
        # only on the first (usually 00:00) row of each day and is None on the
        # 3-hourly rows below it. It is also stored inconsistently (real datetime
        # in most sheets, day-first text like "16-06-2008" in others). Parse both
        # forms and forward-fill — like serial/name/basin — so no fix is dropped.
        date_cell = S.parse_date(get(row, "date"))
        if date_cell is not None:
            cur_date = date_cell

        minutes = S.parse_time(get(row, "time"))
        lat, lon = S.parse_latlon(get(row, "lat"), get(row, "lon"))
        ci_no = S.to_float(get(row, "ci_no"))
        pressure = S.to_float(get(row, "pressure"))
        wind = S.to_float(get(row, "wind"))
        pressure_drop = S.to_float(get(row, "pressure_drop"))
        grade = S.normalize_grade(get(row, "grade"))

        # Usually a fix has both coordinates. A handful of rows are missing one
        # — the cell is blank, or reads "Over land" once the system is inland
        # (1982 #10, 2008 RASHMI, 2017 #7) — while still carrying a real time,
        # pressure, wind and grade. Those are observations with an incomplete
        # position, not remarks, so keep them with NaN for the missing
        # coordinate rather than discarding the fix outright.
        has_intensity = (
            ci_no == ci_no
            or pressure == pressure
            or wind == wind
            or pressure_drop == pressure_drop
            or grade is not None
        )
        has_position = (lat == lat and lon == lon) or ((lat == lat or lon == lon) and has_intensity)

        is_track = (
            storm_no > 0 and isinstance(cur_date, datetime) and minutes is not None and has_position
        )

        if is_track:
            observations.append(
                {
                    "year": year,
                    "storm_no": storm_no,
                    "serial": cur_serial,
                    "basin": cur_basin,
                    "name": cur_name,
                    "time": cur_date + timedelta(minutes=minutes),
                    "_date": cur_date,
                    "_minutes": minutes,
                    "lat": lat,
                    "lon": lon,
                    "ci_no": ci_no,
                    "pressure": pressure,
                    "wind": wind,
                    "pressure_drop": pressure_drop,
                    "grade": grade,
                    "oci": S.to_float(get(row, "oci")),
                    "oci_diameter": S.to_float(get(row, "oci_diameter")),
                }
            )
        elif storm_no > 0:
            text = _remark_text(row)
            if text:
                remarks.append(
                    {
                        "year": year,
                        "storm_no": storm_no,
                        "serial": cur_serial,
                        "date": cur_date if isinstance(cur_date, datetime) else pd.NaT,
                        "remark": text,
                    }
                )

    _resolve_sheet_dates(year, observations)
    return observations, remarks


def _resolve_sheet_dates(year: int, observations: list[dict]) -> None:
    """Fill each observation's ``time_resolved`` from its storm's date sequence.

    Must run here, while the rows are still in workbook order: the resolver
    infers the intended calendar from the order the fixes appear in the sheet,
    which is lost once the frame is sorted by the (possibly wrong) timestamp.
    ``time`` itself is left exactly as the workbook has it.
    """
    from . import qc

    by_storm: dict[int, list[dict]] = {}
    for o in observations:
        by_storm.setdefault(o["storm_no"], []).append(o)

    for recs in by_storm.values():
        fixed = qc.resolve_dates([r["_date"] for r in recs], year)
        for r, d in zip(recs, fixed):
            r["time_resolved"] = d + timedelta(minutes=r["_minutes"])
    for o in observations:
        o.pop("_date", None)
        o.pop("_minutes", None)


def count_positional_rows(path: PathLike) -> dict[int, int]:
    """Count, per year, rows that carry a real fix — a usable position and a
    valid HHMM time — under a storm.

    This is deliberately **independent of the date handling and of the
    storm-boundary rules** (where the fiddly parsing lives): it answers "how many
    track fixes does the workbook contain?" so the pipeline can verify the parser
    captured all of them and never silently drops rows again.

    It applies the same position test as :func:`parse_sheet` — both coordinates,
    or one coordinate on a row that also carries intensity data — so the count is
    an exact expectation rather than a lower bound.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        counts: dict[int, int] = {}
        for year, ws in _iter_year_sheets(wb):
            rows = ws.iter_rows(values_only=True)
            colmap = None
            for row in rows:
                if S.is_header_row(row):
                    colmap = S.detect_columns(row)
                    break
            if colmap is None:
                continue

            def get(row, field, colmap=colmap):
                idx = colmap.get(field)
                if idx is None or idx >= len(row):
                    return None
                return row[idx]

            cur_serial = None
            n = 0
            for row in rows:
                if not any(c is not None for c in row):
                    continue
                serial = get(row, "serial")
                if serial is not None:
                    try:
                        cur_serial = int(float(serial))
                    except (TypeError, ValueError):
                        pass
                lat, lon = S.parse_latlon(get(row, "lat"), get(row, "lon"))
                minutes = S.parse_time(get(row, "time"))
                has_intensity = (
                    any(
                        S.to_float(get(row, f)) == S.to_float(get(row, f))
                        for f in ("ci_no", "pressure", "wind", "pressure_drop")
                    )
                    or S.normalize_grade(get(row, "grade")) is not None
                )
                has_position = (lat == lat and lon == lon) or (
                    (lat == lat or lon == lon) and has_intensity
                )
                if cur_serial is not None and has_position and minutes is not None:
                    n += 1
            counts[year] = n
    finally:
        wb.close()
    return counts


def _storm_id(year: int, storm_no: int) -> str:
    return f"{year}-{storm_no:03d}"


def parse_workbook(path: PathLike) -> dict[str, pd.DataFrame]:
    """Parse a workbook file into ``{"observations", "remarks", "storms"}`` frames."""
    import openpyxl  # deferred: only the pipeline parses raw workbooks.

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        all_obs: list[dict] = []
        all_rem: list[dict] = []
        for year, ws in _iter_year_sheets(wb):
            obs, rem = parse_sheet(year, ws)
            all_obs.extend(obs)
            all_rem.extend(rem)
    finally:
        wb.close()

    obs = pd.DataFrame(
        all_obs,
        columns=["year", "storm_no", "serial", "basin", "name", "time", "time_resolved"]
        + [f for f in S.FIELDS if f in S.NUMERIC_FIELDS]
        + ["grade"],
    )
    if not obs.empty:
        obs.insert(0, "storm_id", [_storm_id(y, n) for y, n in zip(obs["year"], obs["storm_no"])])
        obs = obs.drop(columns="storm_no")
        obs["grade"] = pd.Categorical(obs["grade"], categories=S.GRADE_ORDER, ordered=True)
        obs["basin"] = obs["basin"].astype("category")
        obs = obs.sort_values(["storm_id", "time"], kind="stable").reset_index(drop=True)
        # observation index within each storm (0-based)
        obs["step"] = obs.groupby("storm_id", sort=False).cumcount()
        # Non-destructive QC: flag isolated position spikes, and mis-keyed dates
        # (both are source data-entry errors; the source values stay untouched —
        # `time` is the workbook's date, `time_resolved` the corrected one).
        from . import qc

        obs["pos_suspect"] = qc.flag_positions(obs)
        obs["date_suspect"] = obs["time_resolved"].ne(obs["time"])

    rem = pd.DataFrame(all_rem, columns=["year", "storm_no", "serial", "date", "remark"])
    if not rem.empty:
        rem.insert(0, "storm_id", [_storm_id(y, n) for y, n in zip(rem["year"], rem["storm_no"])])
        rem = rem.drop(columns="storm_no")

    storms = _summarize_storms(obs)
    return {"observations": obs, "remarks": rem, "storms": storms}


def _summarize_storms(obs: pd.DataFrame) -> pd.DataFrame:
    if obs.empty:
        return pd.DataFrame(
            columns=[
                "storm_id",
                "year",
                "serial",
                "name",
                "basin",
                "start_time",
                "end_time",
                "n_obs",
                "peak_grade",
                "max_wind",
                "min_pressure",
            ]
        )

    def peak_grade(s):
        s = s.dropna()
        return s.max() if len(s) else None

    g = obs.groupby("storm_id", sort=False)
    storms = g.agg(
        year=("year", "first"),
        serial=("serial", "first"),
        name=("name", "first"),
        basin=("basin", "first"),
        start_time=("time", "min"),
        end_time=("time", "max"),
        n_obs=("time", "size"),
        max_wind=("wind", "max"),
        min_pressure=("pressure", "min"),
    ).reset_index()
    storms["peak_grade"] = g["grade"].apply(peak_grade).values
    return storms
