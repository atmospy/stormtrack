"""Lightweight quality-control flags for the parsed track.

The IMD workbook is hand-maintained and contains occasional data-entry errors —
most visibly single fixes with a corrupted latitude/longitude that place a storm
hundreds of km off its track (e.g. 1989-008's ``40.8°N`` fix). We don't alter the
source values; instead we *flag* them so users can filter or interpolate.

The check is deliberately conservative: a fix is flagged only when it is an
**isolated spike** — the implied translation speed both *into* it (from the
previous fix) and *out of* it (to the next fix) exceeds a physical cap. That
catches a single bad coordinate between two good ones without touching the good
fixes on either side, and essentially never fires on a genuinely fast storm.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Tropical cyclones translate at up to ~30 kt (~55 km/h); extratropical
# transition can be faster. 110 km/h is well above any real motion, so anything
# beyond it over a 3-6 h step implies a corrupted position, not real movement.
MAX_TRANSLATION_KMH = 110.0


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def flag_positions(observations: pd.DataFrame, max_kmh: float = MAX_TRANSLATION_KMH) -> pd.Series:
    """Return a boolean Series (aligned to ``observations``) flagging fixes whose
    position implies an impossible translation speed from *both* neighbours.

    Source coordinates are never modified — this only marks suspects.
    """
    suspect = pd.Series(False, index=observations.index)
    if observations.empty or not {"storm_id", "time", "lat", "lon"} <= set(observations.columns):
        return suspect

    for _, g in observations.groupby("storm_id", sort=False):
        if len(g) < 3:
            continue
        g = g.sort_values("time")
        lat, lon = g["lat"].to_numpy(dtype="float64"), g["lon"].to_numpy(dtype="float64")
        dt_h = np.diff(g["time"].to_numpy()).astype("timedelta64[s]").astype("float64") / 3600.0
        dist = _haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
        with np.errstate(invalid="ignore", divide="ignore"):
            speed = np.where(dt_h > 0, dist / dt_h, np.nan)  # speed[j] spans fix j -> j+1
        # interior fix j (1..n-2) is a spike when the segments on both sides are fast
        spike = (speed[:-1] > max_kmh) & (speed[1:] > max_kmh)
        suspect.loc[g.index[1:-1]] = spike

    return suspect


# Cyclones live for days, not weeks; a fix whose date sits this far from the rest
# of its storm is almost certainly a data-entry error rather than real duration.
MAX_STORM_SPREAD_DAYS = 15

# Consecutive dated blocks within one storm advance by a day at a time. A little
# slack absorbs genuine gaps in the record without admitting a transposed date.
MAX_BLOCK_GAP_DAYS = 3


def _date_candidates(d, year: int):
    """Readings of a Date cell, most-trusted first.

    The workbook's dates carry two recurring keying errors, both of which leave
    the *position* data untouched and so are invisible on a map:

    * day and month transposed — a cell typed day-first as ``1/5/2008``
      (1 May) but stored by the spreadsheet month-first as 5 January;
    * a mis-keyed year (1989 on a row in the 1988 sheet).

    Both are offered here as alternatives to the stored value;
    :func:`resolve_dates` decides between them from the storm's own sequence.
    """
    import datetime as _dt

    out = [d]

    def _add(x):
        if x is not None and x not in out:
            out.append(x)

    def _swap(x):
        try:
            return _dt.datetime(x.year, x.day, x.month)
        except (ValueError, AttributeError):
            return None

    _add(_swap(d))
    if d.year != year:
        try:
            snapped = d.replace(year=year)
        except ValueError:
            snapped = None
        _add(snapped)
        if snapped is not None:
            _add(_swap(snapped))
    return out


def resolve_dates(dates, year: int):
    """Resolve one storm's Date column, given its fixes **in workbook order**.

    Each dated block is read either as written or as one of the corrections in
    :func:`_date_candidates`; the reading chosen for the storm as a whole is the
    one that advances by whole days and spans the least total time, preferring
    the stored value on ties. Using the storm's internal sequence rather than an
    external archive means storms absent from other archives are repaired too.

    Returns a list of dates aligned with ``dates``; unchanged where the stored
    reading already makes sense, and equal to the input if no reading does.
    """
    if not dates:
        return []

    blocks: list = []
    for d in dates:
        if not blocks or d != blocks[-1]:
            blocks.append(d)
    # A date that recurs after another date has intervened is not a simple
    # keying error; leave such a storm alone rather than guess.
    if len(set(blocks)) != len(blocks):
        return list(dates)

    # Depth-first over the (at most four) readings of each block, keeping only
    # sequences that advance by 1..MAX_BLOCK_GAP_DAYS.
    cands = [_date_candidates(b, year) for b in blocks]
    frontier = [(c, (c,), 0 if k == 0 else 1) for k, c in enumerate(cands[0])]
    for opts in cands[1:]:
        nxt = []
        for cur, path, nsw in frontier:
            for k, o in enumerate(opts):
                if 1 <= (o - cur).days <= MAX_BLOCK_GAP_DAYS:
                    nxt.append((o, path + (o,), nsw + (0 if k == 0 else 1)))
        if not nxt:
            return list(dates)  # no consistent reading; leave the storm as-is
        frontier = nxt

    _, best, _ = min(frontier, key=lambda t: ((t[1][-1] - t[1][0]).days, t[2]))
    mapping = dict(zip(blocks, best))
    return [mapping[d] for d in dates]


def flag_dates(observations: pd.DataFrame, min_gap_days: int = MAX_STORM_SPREAD_DAYS):
    """Detect day/month-transposition errors in the Date column.

    Some rows store a date with day and month swapped — e.g. Nargis (2008-001)
    has May 1-3 written as "01-05", "02-05", "03-05" (Jan/Feb/Mar 5), which
    scatters the storm across four months. A fix is flagged when it sits far from
    its storm's median date *and* swapping its day and month brings it back in
    line.

    Returns ``(date_suspect, corrected_time)``: a boolean Series and a copy of
    ``time`` with the swap applied for flagged fixes (source untouched — callers
    opt in via :meth:`stormtrack.BestTracks.clean`).
    """
    suspect = pd.Series(False, index=observations.index)
    corrected = (
        observations["time"].copy()
        if "time" in observations.columns
        else pd.Series(index=observations.index, dtype="datetime64[ns]")
    )
    if observations.empty or not {"storm_id", "time"} <= set(observations.columns):
        return suspect, corrected

    day = pd.Timedelta(days=1)
    for _, g in observations.groupby("storm_id", sort=False):
        if len(g) < 3:
            continue
        med = g["time"].median()
        for idx, t in g["time"].items():
            if pd.isna(t) or t.day > 12 or t.month > 12 or t.day == t.month:
                continue  # not swappable / no change
            try:
                swapped = t.replace(month=t.day, day=t.month)
            except ValueError:
                continue
            orig_gap = abs((t - med) / day)
            swap_gap = abs((swapped - med) / day)
            if orig_gap > min_gap_days and swap_gap <= min_gap_days:
                suspect.loc[idx] = True
                corrected.loc[idx] = swapped

    return suspect, corrected
