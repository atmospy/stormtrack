"""Verify track/intensity forecasts against a best track, and build forecast cones.

Method (after NHC practice, https://www.nhc.noaa.gov/verification/verify4.shtml):

* a forecast error is the great-circle distance between the forecast position and
  the best-track position *at the verifying time* (``init + tau``);
* a forecast counts only if the system was a tropical or subtropical cyclone at
  both the forecast and verifying times (when the best track carries a storm type);
* the NHC cone is the area swept by circles at each forecast point whose radii
  contain two-thirds (67 %) of the previous five years' official track errors
  (https://www.nhc.noaa.gov/aboutcone.shtml). :func:`error_radii` computes such
  radii from any set of errors and :func:`cone_polygons` builds the shape.

The best track may come from any imdtrack source, so JTWC or NHC forecasts for a
North Indian Ocean storm can be scored against the IMD best track.

Note: NHC's published 2026 experimental cone uses ellipses at the 90th percentile
instead of circles; this module implements the circle definition.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .analysis import haversine_km
from .atcf import TC_TYPES

KM_PER_NM = 1.852


def _bearing(lat1, lon1, lat2, lon2):
    """Initial bearing (deg clockwise from north) from point 1 to point 2."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians((np.asarray(lon2, float) - np.asarray(lon1, float) + 180) % 360 - 180)
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360


def _best_at(best: pd.DataFrame, times: pd.Series, max_gap_hours: float) -> pd.DataFrame:
    """Best-track position, wind, pressure, type and heading at ``times`` (one storm).

    Linear interpolation between the bracketing fixes; NaN when the fixes are more
    than ``max_gap_hours`` apart or ``times`` is outside the track.
    """
    b = best.sort_values("time").drop_duplicates("time").reset_index(drop=True)
    t = b["time"].to_numpy("datetime64[ns]").astype("int64") / 3.6e12  # hours
    q = pd.to_datetime(times).to_numpy("datetime64[ns]").astype("int64") / 3.6e12
    i1 = np.searchsorted(t, q, side="left").clip(1, max(len(b) - 1, 1))
    i0 = i1 - 1
    out = pd.DataFrame(index=range(len(q)))
    if len(b) < 2:
        return out.assign(lat=np.nan, lon=np.nan, wind=np.nan, pressure=np.nan, ty=None,
                          heading=np.nan)  # fmt: skip
    span = t[i1] - t[i0]
    w = np.where(span > 0, (q - t[i0]) / np.where(span > 0, span, 1), 0.0)
    exact = (np.abs(q - t[i0]) < 1e-6) | (
        np.abs(q - t[i1]) < 1e-6
    )  # on a fix: nothing to interpolate
    ok = (q >= t[0] - 1e-6) & (q <= t[-1] + 1e-6) & ((span <= max_gap_hours + 1e-6) | exact)
    lon_u = np.degrees(np.unwrap(np.radians(b["lon"].to_numpy())))
    for col, arr in (("lat", b["lat"].to_numpy()), ("lon", lon_u)):
        out[col] = np.where(ok, arr[i0] + w * (arr[i1] - arr[i0]), np.nan)
    out["lon"] = (out["lon"] + 180) % 360 - 180
    for col in ("wind", "pressure"):
        a = b[col].to_numpy(dtype=float) if col in b else np.full(len(b), np.nan)
        out[col] = np.where(ok, a[i0] + w * (a[i1] - a[i0]), np.nan)
    nearest = np.where(w >= 0.5, i1, i0)  # a storm type can't be interpolated: take the closer fix
    out["ty"] = np.where(ok, b["ty"].to_numpy()[nearest], None) if "ty" in b else None
    out["heading"] = np.where(
        ok, _bearing(b["lat"].to_numpy()[i0], b["lon"].to_numpy()[i0],
                     b["lat"].to_numpy()[i1], b["lon"].to_numpy()[i1]), np.nan)  # fmt: skip
    return out


def forecast_errors(
    forecasts: pd.DataFrame,
    best,
    tc_only: bool = True,
    max_gap_hours: float = 6.0,
    min_tau: int = 0,
) -> pd.DataFrame:
    """Score forecasts against a best track, one row per forecast point.

    Parameters
    ----------
    forecasts : an :func:`~imdtrack.atcf.parse_atcf` frame (an f-deck from
        :func:`~imdtrack.realtime.get_forecast`, or an a-deck from
        :func:`~imdtrack.realtime.get_guidance`; many techs and cycles are fine).
    best : a :class:`~imdtrack.BestTracks` or observations frame. With one storm in
        it, every forecast is scored against that storm (so the forecast and best
        track may have different ids, e.g. a JTWC forecast vs the IMD best track);
        with several, forecasts are matched on ``atcf_id == storm_id``.
    tc_only : require a tropical/subtropical cyclone at both forecast and verifying
        time, when the data carry a storm type (``ty``).
    max_gap_hours : do not interpolate the best track across larger gaps.

    Columns: ``atcf_id, tech, init, tau, time, f_*``/``b_*`` (lat, lon, vmax, mslp),
    ``track_err_km``, ``along_km`` (positive = forecast ahead of the best-track
    motion), ``cross_km`` (positive = right of motion), ``vmax_err`` and
    ``mslp_err`` (forecast minus best).
    """
    obs = best.observations if hasattr(best, "observations") else best
    f = forecasts[forecasts["tau"] >= min_tau]
    single = obs["storm_id"].nunique() == 1
    parts = []
    for aid, fg in f.groupby("atcf_id", sort=False):
        bs = obs if single else obs[obs["storm_id"] == aid]
        if bs.empty:
            continue
        fg = fg.reset_index(drop=True)
        b = _best_at(bs, fg["time"], max_gap_hours)
        e = pd.DataFrame(
            {
                "atcf_id": aid, "tech": fg["tech"], "init": fg["init"], "tau": fg["tau"],
                "time": fg["time"], "f_lat": fg["lat"], "f_lon": fg["lon"],
                "f_vmax": fg["vmax"], "f_mslp": fg["mslp"], "b_lat": b["lat"],
                "b_lon": b["lon"], "b_vmax": b["wind"], "b_mslp": b["pressure"],
            }
        )  # fmt: skip
        if tc_only:
            keep = pd.Series(True, index=e.index)
            if "ty" in fg:
                init_ty = fg[fg["tau"] == 0].set_index(["init", "tech"])["ty"]
                key = list(zip(fg["init"], fg["tech"]))
                ity = pd.Series([init_ty.get(k) for k in key], index=e.index)
                keep &= ity.isna() | ity.isin(TC_TYPES)
            if b["ty"].notna().any():
                keep &= b["ty"].isna() | b["ty"].isin(TC_TYPES)
            e = e[keep]
            b = b[keep]
        d = haversine_km(e["f_lat"], e["f_lon"], e["b_lat"], e["b_lon"])
        brg = _bearing(e["b_lat"], e["b_lon"], e["f_lat"], e["f_lon"])
        delta = np.radians(brg - b["heading"])
        e["track_err_km"] = d
        e["along_km"] = d * np.cos(delta)
        e["cross_km"] = d * np.sin(delta)
        e["vmax_err"] = e["f_vmax"] - e["b_vmax"]
        e["mslp_err"] = e["f_mslp"] - e["b_mslp"]
        parts.append(e.dropna(subset=["track_err_km"]))
    if not parts:
        return pd.DataFrame(columns=["atcf_id", "tech", "init", "tau", "time", "track_err_km"])
    return pd.concat(parts, ignore_index=True)


def error_summary(errors: pd.DataFrame, by=("tech", "tau")) -> pd.DataFrame:
    """Mean error statistics per ``by`` group: sample size, mean/median/67th-percentile
    track error (km), mean along/cross-track bias, and wind mean error (bias) and MAE (kt)."""
    g = errors.groupby(list(by))
    return pd.DataFrame(
        {
            "n": g.size(),
            "track_mean_km": g["track_err_km"].mean(),
            "track_median_km": g["track_err_km"].median(),
            "track_p67_km": g["track_err_km"].quantile(0.67),
            "along_bias_km": g["along_km"].mean(),
            "cross_bias_km": g["cross_km"].mean(),
            "vmax_bias_kt": g["vmax_err"].mean(),
            "vmax_mae_kt": g["vmax_err"].apply(lambda s: s.abs().mean()),
        }
    ).reset_index()


def error_radii(errors: pd.DataFrame, pct: float = 67.0, min_n: int = 10, units: str = "km"):
    """Cone-circle radii by lead time: the ``pct``-th percentile of track error.

    NHC uses ``pct=67`` of the previous five years' official-forecast errors. Lead
    times with fewer than ``min_n`` samples are dropped. Returns a ``Series`` indexed
    by ``tau`` (hours); ``units`` is ``"km"`` or ``"nm"``.
    """
    if units not in ("km", "nm"):
        raise ValueError("units must be 'km' or 'nm'")
    g = errors.groupby("tau")["track_err_km"]
    r = g.quantile(pct / 100.0)[g.size() >= min_n]
    return (r / KM_PER_NM if units == "nm" else r).rename(f"p{pct:g}_{units}")


def _circle(lat, lon, radius_km, n=72):
    """Points of a great-circle circle of ``radius_km`` around (lat, lon)."""
    brg = np.radians(np.linspace(0, 360, n, endpoint=False))
    ang = radius_km / 6371.0088
    p1, l1 = np.radians(lat), np.radians(lon)
    p2 = np.arcsin(np.sin(p1) * np.cos(ang) + np.cos(p1) * np.sin(ang) * np.cos(brg))
    l2 = l1 + np.arctan2(
        np.sin(brg) * np.sin(ang) * np.cos(p1), np.cos(ang) - np.sin(p1) * np.sin(p2)
    )
    return np.column_stack([np.degrees(l2), np.degrees(p2)])


def _hull(pts):
    """Convex hull (Andrew's monotone chain) of an (n, 2) array, counter-clockwise."""
    p = sorted(map(tuple, pts))
    if len(p) <= 2:
        return np.array(p)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    for q in reversed(p):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return np.array(lower[:-1] + upper[:-1])


def cone_polygons(forecast: pd.DataFrame, radii_km, n: int = 72) -> list:
    """Polygons (``(m, 2)`` lon/lat arrays) whose union is the forecast cone.

    ``radii_km`` maps lead time (hours) to circle radius (km), e.g. the output of
    :func:`error_radii`; radii for other lead times are interpolated linearly, with
    zero radius at ``tau == 0``. One polygon is returned per forecast segment (the
    convex hull of its two end circles — the "sweep" of the circle between points).
    Draw them with identical fill and no edge to get the cone.
    """
    r = pd.Series(radii_km).sort_index()
    f = forecast.sort_values("tau").drop_duplicates("tau")
    f = f[f["tau"] <= r.index.max()]
    if len(f) < 2:
        return []
    taus = np.concatenate([[0], r.index.to_numpy(float)])
    vals = np.concatenate([[0.0], r.to_numpy(float)])
    rad = np.interp(f["tau"].to_numpy(float), taus, vals)
    # work in a locally unwrapped longitude so hulls don't tear across the dateline
    lon = np.degrees(np.unwrap(np.radians(f["lon"].to_numpy())))
    circles = [_circle(la, lo, ra, n) for la, lo, ra in zip(f["lat"], lon, rad)]
    # _circle returns (lon, lat) around an unwrapped centre; keep that frame
    return [_hull(np.vstack([circles[i], circles[i + 1]])) for i in range(len(circles) - 1)]
