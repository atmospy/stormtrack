"""Parse ATCF text decks (best tracks, forecasts, model guidance).

The Automated Tropical Cyclone Forecasting System (ATCF; Sampson and Schrader
2000) is the comma-separated text format in which NHC and JTWC exchange tracks.
One format covers three kinds of deck, told apart by the ``tech`` column:

* **b-deck** (best track): ``tech == "BEST"``, ``tau == 0``
* **f-deck / ``.fst``** (the agency's current forecast): e.g. ``OFCL`` at ``tau`` 0..120
* **a-deck** (every model's forecast, by initial time): ``GFS``-like ``AVNO``, ``HWRF`` ...

:func:`parse_atcf` returns one row per (initial time, tech, tau) with wind radii
spread over columns (``r34_ne`` ... ``r64_nw``) rather than repeated rows.

References
----------
Sampson, C. R., and A. J. Schrader, 2000: The Automated Tropical Cyclone
Forecasting System (version 3.2). *Bull. Amer. Meteor. Soc.*, **81**, 1231–1240,
doi:10.1175/1520-0477(2000)081<1231:TATCFS>2.3.CO;2.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import numpy as np
import pandas as pd

# ATCF field order (Sampson and Schrader 2000); only the leading fields are used.
_FIELDS = [
    "basin", "cy", "time", "technum", "tech", "tau", "lat", "lon", "vmax", "mslp", "ty",
    "rad", "windcode", "rad1", "rad2", "rad3", "rad4", "pouter", "router", "rmw", "gusts",
    "eye", "subregion", "maxseas", "initials", "dir", "speed", "stormname",
]  # fmt: skip

# Plausibility bounds: values outside become NaN (0 is the ATCF "missing" code).
VMAX_RANGE = (10.0, 250.0)  # kt
MSLP_RANGE = (800.0, 1040.0)  # hPa

# ATCF storm types that count as a tropical or subtropical cyclone
# (TD, TS, TY, ST, TC, HU, SD, SS); the rest are disturbances, lows, waves, ...
TC_TYPES = {"TD", "TS", "TY", "ST", "TC", "HU", "SD", "SS"}

# ATCF basin code -> the IBTrACS genesis-basin code used elsewhere in stormtrack.
BASIN_TO_IBTRACS = {"AL": "NA", "EP": "EP", "CP": "EP", "WP": "WP", "IO": "NI", "SH": "SH"}


def sh_basin(lon0: float) -> str:
    """IBTrACS Southern-Hemisphere basin of a storm from its genesis longitude: South Indian
    ``SI`` (20°E–135°E), South Pacific ``SP`` (135°E–120°W), otherwise South Atlantic ``SA``.
    ATCF has a single ``SH`` basin, so this recovers the finer IBTrACS split."""
    if 20 <= lon0 < 135:
        return "SI"
    if lon0 >= 135 or lon0 < -120:
        return "SP"
    return "SA"


_QUADS = ("ne", "se", "sw", "nw")
_NUMBER_WORDS = (
    "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN FIFTEEN "
    "SIXTEEN SEVENTEEN EIGHTEEN NINETEEN TWENTY"
).split()
_NUMBERED = set(_NUMBER_WORDS) | {
    f"{t}{'-' if u else ''}{u}".strip()
    for t in ("TWENTY", "THIRTY", "FORTY", "FIFTY")
    for u in [""] + _NUMBER_WORDS[:9]
}
_NO_NAME = {"", "INVEST", "NONAME", "UNNAMED"}


def _coord(v: str) -> float:
    """``'148N'`` -> 14.8, ``'0866E'`` -> 86.6, ``'458W'`` -> -45.8 (tenths of a degree)."""
    v = v.strip()
    if len(v) < 2 or v[-1] not in "NSEW" or not v[:-1].lstrip("-").isdigit():
        return np.nan
    x = int(v[:-1]) / 10.0
    return -x if v[-1] in "SW" else x


def _clean_name(raw: str) -> Optional[str]:
    n = raw.strip().upper()
    if n in _NO_NAME or n in _NUMBERED or n.startswith("GENESIS"):
        return None
    return n


def parse_atcf(source) -> pd.DataFrame:
    """Parse ATCF text (a string, bytes, or an open file) into a tidy DataFrame.

    Columns: ``atcf_id, basin, cy, year, init, tech, tau, time, lat, lon, vmax, mslp,
    ty, name`` plus ``r34_ne ... r64_nw`` (wind radii, nautical miles), ``rmw``,
    ``roci`` and ``poci``. ``init`` is the deck's date-time group, ``time`` the valid
    time (``init + tau``); longitudes are wrapped to [-180, 180). Lines that do not
    parse are skipped.
    """
    if hasattr(source, "read"):
        source = source.read()
    if isinstance(source, bytes):
        source = source.decode("utf-8", "replace")

    rows = []
    for line in io.StringIO(source):
        f = [p.strip() for p in line.rstrip("\n").split(",")]
        if len(f) < 11 or not re.fullmatch(r"\d{10}", f[2]) or not f[5].lstrip("-").isdigit():
            continue
        f += [""] * (len(_FIELDS) - len(f))
        rec = dict(zip(_FIELDS, f[: len(_FIELDS)]))
        rows.append(rec)
    if not rows:
        return _empty()

    d = pd.DataFrame(rows)
    out = pd.DataFrame()
    out["basin"] = d["basin"].str.upper()
    out["cy"] = pd.to_numeric(d["cy"], errors="coerce").astype("Int64")
    out["init"] = pd.to_datetime(d["time"], format="%Y%m%d%H")
    out["tech"] = d["tech"].str.upper()
    out["tau"] = d["tau"].astype(int)
    out["time"] = out["init"] + pd.to_timedelta(out["tau"], unit="h")
    out["lat"] = d["lat"].map(_coord)
    out["lon"] = (d["lon"].map(_coord) + 180) % 360 - 180
    out["vmax"] = pd.to_numeric(d["vmax"], errors="coerce")
    out["mslp"] = pd.to_numeric(d["mslp"], errors="coerce")
    out["vmax"] = out["vmax"].where(out["vmax"].between(*VMAX_RANGE))
    out["mslp"] = out["mslp"].where(out["mslp"].between(*MSLP_RANGE))
    out["ty"] = d["ty"].str.upper()
    for c in ("rmw", "router", "pouter"):
        v = pd.to_numeric(d[c], errors="coerce")
        out[{"rmw": "rmw", "router": "roci", "pouter": "poci"}[c]] = v.where(v > 0)
    out["name"] = d["stormname"].map(_clean_name)
    out["year"] = out["init"].dt.year
    out["atcf_id"] = out["basin"] + out["cy"].astype(str).str.zfill(2) + out["year"].astype(str)

    # wind radii: one input line per (position, radius threshold) -> columns
    rad = pd.to_numeric(d["rad"], errors="coerce")
    rad = rad.replace({0: np.nan, 35: 34})  # 0 = none; a few decks write 35 for 34 kt
    for k, q in enumerate(_QUADS, start=1):
        r = pd.to_numeric(d[f"rad{k}"], errors="coerce")
        for thr in (34, 50, 64):
            out[f"r{thr}_{q}"] = r.where((rad == thr) & (r > 0))

    key = ["atcf_id", "init", "tech", "tau"]
    agg = {c: "first" for c in out.columns if c not in key}
    radii = [c for c in out.columns if re.fullmatch(r"r(34|50|64)_(ne|se|sw|nw)", c)]
    for c in radii:
        agg[c] = "max"  # take the line that carries the value for this threshold
    out = out.groupby(key, sort=False, as_index=False).agg(agg)
    cols = ["atcf_id", "basin", "cy", "year", "init", "tech", "tau", "time", "lat", "lon",
            "vmax", "mslp", "ty", "name", "rmw", "roci", "poci", *radii]  # fmt: skip
    return out[cols].sort_values(["init", "tech", "tau"], kind="stable").reset_index(drop=True)


def _empty() -> pd.DataFrame:
    cols = ["atcf_id", "basin", "cy", "year", "init", "tech", "tau", "time", "lat", "lon",
            "vmax", "mslp", "ty", "name"]  # fmt: skip
    return pd.DataFrame(columns=cols)


def best_track_frame(deck: pd.DataFrame) -> pd.DataFrame:
    """Reshape a parsed b-deck into the ``observations`` schema used by stormtrack.

    Keeps ``tech == "BEST"`` rows, drops duplicate times (the last entry wins, as
    asynoptic records are appended), and adds ``storm_id`` (the ATCF id), ``basin``
    in IBTrACS codes, ``wind`` (kt), ``pressure`` (hPa) and ``step``.
    """
    b = deck[deck["tech"] == "BEST"] if len(deck) else deck
    if b.empty:
        return pd.DataFrame(
            columns=["storm_id", "year", "serial", "basin", "name", "time", "lat", "lon", "wind",
                     "pressure", "ty", "step"]  # fmt: skip
        )
    b = b.drop_duplicates(["atcf_id", "time"], keep="last").sort_values(["atcf_id", "time"])
    name = b["atcf_id"].map(b.dropna(subset=["name"]).groupby("atcf_id")["name"].last())
    obs = pd.DataFrame(
        {
            "storm_id": b["atcf_id"].to_numpy(),
            "year": b["year"].to_numpy(),
            "serial": b["cy"].astype("int64").to_numpy(),
            "basin": b["basin"].map(BASIN_TO_IBTRACS).fillna(b["basin"]).to_numpy(),
            "atcf_basin": b["basin"].to_numpy(),
            "name": name.to_numpy(),
            "time": b["time"].to_numpy(),
            "lat": b["lat"].to_numpy(),
            "lon": b["lon"].to_numpy(),
            "wind": b["vmax"].to_numpy(),
            "pressure": b["mslp"].to_numpy(),
            "ty": b["ty"].to_numpy(),
        }
    )  # fmt: skip
    obs["step"] = obs.groupby("storm_id", sort=False).cumcount()
    sh = obs["atcf_basin"] == "SH"
    if sh.any():  # a storm keeps the basin it formed in
        lon0 = obs.groupby("storm_id", sort=False)["lon"].transform("first")
        obs.loc[sh, "basin"] = lon0[sh].map(sh_basin)
    return obs.reset_index(drop=True)
