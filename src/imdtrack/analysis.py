"""Source-agnostic cyclone analysis for the IMD record and IBTrACS.

Every function takes either a :class:`~imdtrack.BestTracks` or a bare
observations ``DataFrame`` with the columns ``storm_id, time, lat, lon, wind``
(and ``year, basin, name, pressure`` where noted), so the same code runs on
``imd.load()`` and ``imd.load_ibtracs()``. Wind is in knots; note that agencies
average it over different periods (see :mod:`imdtrack.ibtracs`).

>>> import imdtrack as imd
>>> bt = imd.load()
>>> imd.analysis.lifetime_max(bt).head()
>>> imd.analysis.rapid_intensification(bt)           # >= 30 kt in 24 h
>>> imd.analysis.annual_counts(bt)                   # storms per year by strength
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Wind thresholds (kt, lifetime-maximum) used for the strength classes.
THRESHOLDS = {"tropical_storm": 34, "hurricane": 64, "major": 96}


def _obs(x) -> pd.DataFrame:
    return x.observations if hasattr(x, "observations") else x


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (km) between points; arguments broadcast like numpy."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(
        (np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float) + 180) % 360 - 180
    )
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


def lifetime_max(x) -> pd.DataFrame:
    """One row per storm: lifetime-maximum intensity and where/when it occurred.

    Columns: ``storm_id, name, year, basin, start_time, end_time, duration_days,
    lmi_wind, lmi_time, lmi_lat, lmi_lon, min_pressure, genesis_lat, genesis_lon``.
    """
    obs = _obs(x).sort_values(["storm_id", "time"]).reset_index(drop=True)
    g = obs.groupby("storm_id", sort=False)
    first = g.first()
    peak = obs.loc[obs["wind"].notna()].groupby("storm_id", sort=False)["wind"].idxmax()
    pk = obs.loc[peak.to_numpy()].set_index("storm_id")
    out = pd.DataFrame(
        {
            "name": first["name"] if "name" in first else None,
            "year": first["year"] if "year" in first else first["time"].dt.year,
            "basin": first["basin"] if "basin" in first else None,
            "start_time": g["time"].min(),
            "end_time": g["time"].max(),
            "lmi_wind": pk["wind"],
            "lmi_time": pk["time"],
            "lmi_lat": pk["lat"],
            "lmi_lon": pk["lon"],
            "min_pressure": g["pressure"].min() if "pressure" in obs else np.nan,
            "genesis_lat": first["lat"],
            "genesis_lon": first["lon"],
        }
    )
    out["duration_days"] = (out["end_time"] - out["start_time"]).dt.total_seconds() / 86400
    return out.reset_index()


def intensity_change(x, hours: float = 24.0) -> pd.DataFrame:
    """Observations plus ``dwind``: wind change over the next ``hours`` (kt).

    The later fix is looked up by *time*, not row position, so it works for both
    3- and 6-hourly data; fixes with no observation exactly ``hours`` later get NaN.
    """
    obs = _obs(x).copy()
    later = obs[["storm_id", "time", "wind"]].copy()
    later["time"] = later["time"] - pd.Timedelta(hours=hours)
    later = later.drop_duplicates(["storm_id", "time"]).rename(columns={"wind": "_wind_later"})
    obs = obs.merge(later, on=["storm_id", "time"], how="left")
    obs["dwind"] = obs.pop("_wind_later") - obs["wind"]
    return obs


def rapid_intensification(x, hours: float = 24.0, threshold: float = 30.0) -> pd.DataFrame:
    """Per storm: strongest ``hours`` intensification and whether it reached ``threshold``.

    The default (>= 30 kt / 24 h) is the standard rapid-intensification (RI)
    definition of Kaplan & DeMaria (2003). Columns: ``storm_id, name, year, basin,
    max_dwind, ri_time, ri_lat, ri_lon, rapid`` (``ri_*`` = start of the strongest burst).
    """
    ic = intensity_change(x, hours)
    ic = ic.dropna(subset=["dwind"])
    idx = ic.groupby("storm_id", sort=False)["dwind"].idxmax()
    top = ic.loc[idx.to_numpy()]
    out = pd.DataFrame(
        {
            "storm_id": top["storm_id"].to_numpy(),
            "name": top["name"].to_numpy() if "name" in top else None,
            "year": top["year"].to_numpy() if "year" in top else top["time"].dt.year.to_numpy(),
            "basin": top["basin"].to_numpy() if "basin" in top else None,
            "max_dwind": top["dwind"].to_numpy(),
            "ri_time": top["time"].to_numpy(),
            "ri_lat": top["lat"].to_numpy(),
            "ri_lon": top["lon"].to_numpy(),
        }
    )
    out["rapid"] = out["max_dwind"] >= threshold
    return out.reset_index(drop=True)


def annual_counts(x, thresholds: Optional[dict] = None, by_basin: bool = False) -> pd.DataFrame:
    """Storms per year whose lifetime-maximum wind reached each threshold.

    ``thresholds`` maps a column name to kt (default: tropical storm 34, hurricane 64,
    major 96). The ``storms`` column counts every storm regardless of intensity.
    """
    thresholds = thresholds or THRESHOLDS
    lm = lifetime_max(x)
    keys = ["year", "basin"] if by_basin else ["year"]
    g = lm.groupby(keys)
    out = g.size().rename("storms").to_frame()
    for name, kt in thresholds.items():
        out[name] = g["lmi_wind"].apply(lambda w, kt=kt: int((w >= kt).sum()))
    return out.reset_index()


def monthly_climatology(x, min_wind: float = 0.0, by_basin: bool = False) -> pd.DataFrame:
    """Mean number of storms per calendar month (by month of genesis).

    Only storms reaching ``min_wind`` are counted. Returns ``month, storms``
    (total), ``per_year`` (total / number of seasons spanned) and, with
    ``by_basin``, one row per basin.
    """
    lm = lifetime_max(x)
    lm = lm[lm["lmi_wind"] >= min_wind]
    n_years = max(int(lm["year"].max() - lm["year"].min()) + 1, 1) if len(lm) else 1
    lm = lm.assign(month=lm["start_time"].dt.month)
    keys = ["basin", "month"] if by_basin else ["month"]
    out = lm.groupby(keys).size().rename("storms").reset_index()
    out["per_year"] = out["storms"] / n_years
    return out


def ace(x, min_wind: float = 34.0, synoptic_only: bool = True) -> pd.DataFrame:
    """Accumulated cyclone energy per storm: ``1e-4 * sum(v^2)`` over fixes >= ``min_wind``.

    ACE is conventionally summed over 6-hourly (00/06/12/18 UTC) fixes, so
    ``synoptic_only`` drops the 3-hourly/interpolated ones. Units: 10^4 kt^2.
    """
    obs = _obs(x)
    if synoptic_only:
        obs = obs[(obs["time"].dt.hour % 6 == 0) & (obs["time"].dt.minute == 0)]
    obs = obs[obs["wind"] >= min_wind]
    g = obs.assign(_e=obs["wind"] ** 2 * 1e-4).groupby("storm_id", sort=False)
    out = g["_e"].sum().rename("ace").reset_index()
    for c in ("year", "basin", "name"):
        if c in obs:
            out[c] = g[c].first().to_numpy()
    return out


def translation_speed(x) -> pd.DataFrame:
    """Observations plus ``speed_kmh`` and ``heading`` (deg from north) from the
    previous fix, per storm. The first fix of each storm is NaN."""
    obs = _obs(x).sort_values(["storm_id", "time"]).copy()
    g = obs.groupby("storm_id", sort=False)
    plat, plon, pt = g["lat"].shift(), g["lon"].shift(), g["time"].shift()
    dist = haversine_km(plat, plon, obs["lat"], obs["lon"])
    hours = (obs["time"] - pt).dt.total_seconds() / 3600
    obs["speed_kmh"] = dist / hours.where(hours > 0)
    dlon = np.radians((obs["lon"] - plon + 180) % 360 - 180)
    p1, p2 = np.radians(plat), np.radians(obs["lat"])
    y = np.sin(dlon) * np.cos(p2)
    xx = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dlon)
    obs["heading"] = (np.degrees(np.arctan2(y, xx)) + 360) % 360
    return obs


def match_controls(
    events: pd.DataFrame,
    pool: pd.DataFrame,
    wind_tol: float = 10.0,
    k: int = 1,
    same_basin: bool = True,
    reuse: bool = False,
) -> pd.DataFrame:
    """Pick control storms matched to each event storm.

    ``events`` and ``pool`` are storm tables indexed by ``storm_id`` with
    ``basin``, ``year`` and ``peak_wind`` columns (e.g. ``lifetime_max(...)`` renamed,
    via ``.set_index("storm_id").rename(columns={"lmi_wind": "peak_wind"})``).
    For each event (strongest first) the ``k`` pool storms in the same basin with
    peak wind within ``wind_tol`` kt and nearest in year are chosen; unless
    ``reuse``, a control is used at most once. Returns ``event, control, rank``.
    """
    used: set = set()
    rows = []
    for sid, e in events.sort_values("peak_wind", ascending=False).iterrows():
        c = (
            pool[~pool.index.isin(used | {sid})]
            if not reuse
            else pool.drop(index=sid, errors="ignore")
        )
        if same_basin:
            c = c[c["basin"] == e["basin"]]
        c = c[(c["peak_wind"] - e["peak_wind"]).abs() <= wind_tol]
        c = c.assign(_dy=(c["year"] - e["year"]).abs(), _dw=(c["peak_wind"] - e["peak_wind"]).abs())
        c = c.sort_values(["_dy", "_dw"]).head(k)
        if not reuse:
            used.update(c.index)
        rows += [{"event": sid, "control": cs, "rank": i} for i, cs in enumerate(c.index)]
    return pd.DataFrame(rows, columns=["event", "control", "rank"])


def storm_windows(storms: pd.DataFrame, pad_days: float = 15.0, freq: str = "6h") -> pd.DataFrame:
    """A regular timeline per storm from ``start - pad`` to ``end + pad``.

    ``storms`` needs ``start_time`` and ``end_time`` (as in ``bt.storms``), indexed
    or keyed by ``storm_id``. Output columns: ``storm_id, time, phase`` (``pre`` /
    ``during`` / ``post``) and ``day`` — days since genesis (pre) or since
    dissipation (post), NaN during. Join it to gridded data (ERA5, satellite...)
    for lifecycle composites.
    """
    st = storms.set_index("storm_id") if "storm_id" in storms.columns else storms
    pad = pd.Timedelta(days=pad_days)
    parts = []
    for sid, s in st.iterrows():
        t = pd.date_range(s["start_time"] - pad, s["end_time"] + pad, freq=freq)
        phase = np.where(t < s["start_time"], "pre", np.where(t > s["end_time"], "post", "during"))
        day = np.where(
            phase == "pre",
            (t - s["start_time"]) / pd.Timedelta(days=1),
            np.where(phase == "post", (t - s["end_time"]) / pd.Timedelta(days=1), np.nan),
        )
        parts.append(pd.DataFrame({"storm_id": sid, "time": t, "phase": phase, "day": day}))
    cols = ["storm_id", "time", "phase", "day"]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def paired_bootstrap(a, b, n_boot: int = 5000, ci: float = 95.0, seed: Optional[int] = 0) -> dict:
    """Mean of ``a - b`` over pairs, with a percentile bootstrap CI over pairs.

    NaN pairs are dropped. Returns ``n, mean_diff, lo, hi`` (NaN CI for n < 2).
    """
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    d = d[~np.isnan(d)]
    if len(d) < 2:
        return {"n": len(d), "mean_diff": float(d.mean()) if len(d) else np.nan,
                "lo": np.nan, "hi": np.nan}  # fmt: skip
    rng = np.random.default_rng(seed)
    boot = rng.choice(d, (n_boot, len(d))).mean(axis=1)
    lo, hi = np.percentile(boot, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return {"n": len(d), "mean_diff": float(d.mean()), "lo": float(lo), "hi": float(hi)}


# WMO/TD-1555 Table 1.2: Vmax(10-min) = K * Vmax(1-min), by exposure.
_VMAX_K = {"at-sea": 0.93, "off-sea": 0.90, "off-land": 0.87, "in-land": 0.84}


def convert_vmax(wind, src_period: int = 60, dst_period: int = 600, exposure: str = "at-sea"):
    """Convert a *maximum* sustained wind between 1-minute and 10-minute averaging.

    Implements Table 1.2 of Harper, Kepert and Ginger (2010), ``Vmax600 = K * Vmax60``
    with K = 0.93 (``"at-sea"``, the default), 0.90 (``"off-sea"``), 0.87
    (``"off-land"``) or 0.84 (``"in-land"``); the reverse divides by K. The authors
    call this an interim measure. Periods are in seconds; the guidelines give **no**
    factor involving 3-min (180 s) winds, so IMD winds cannot be converted with them
    and other pairs raise ``ValueError``.
    """
    if exposure not in _VMAX_K:
        raise ValueError(f"exposure must be one of {sorted(_VMAX_K)}")
    k = _VMAX_K[exposure]
    if (src_period, dst_period) == (60, 600):
        return wind * k
    if (src_period, dst_period) == (600, 60):
        return wind / k
    if src_period == dst_period:
        return wind
    raise ValueError(
        "WMO/TD-1555 Table 1.2 only covers 60 s <-> 600 s maximum winds, "
        f"not {src_period} s -> {dst_period} s"
    )


# IMD intensity classes by 3-min sustained wind (kt): lower bound of each grade.
_GRADE_BOUNDS = [("D", 17), ("DD", 28), ("CS", 34), ("SCS", 48), ("VSCS", 64), ("ESCS", 90),
                 ("SuCS", 120)]  # fmt: skip


def grade_from_wind(wind) -> pd.Categorical:
    """IMD grade (``D`` ... ``SuCS``) from wind in knots; ``NaN`` below 17 kt or missing.

    Uses RSMC New Delhi's thresholds for the 3-minute sustained wind (D 17–27,
    DD 28–33, CS 34–47, SCS 48–63, VSCS 64–89, ESCS 90–119, SuCS >= 120). Applying
    them to another agency's winds (e.g. JTWC's 1-minute) is only approximate.
    """
    from . import _schema as S

    w = np.asarray(wind, dtype=float)
    idx = np.searchsorted([b for _, b in _GRADE_BOUNDS], w, side="right") - 1
    names = np.array([g for g, _ in _GRADE_BOUNDS] + [None], dtype=object)
    idx = np.where(np.isnan(w) | (idx < 0), len(_GRADE_BOUNDS), idx)
    return pd.Categorical(names[idx], categories=S.GRADE_ORDER, ordered=True)
