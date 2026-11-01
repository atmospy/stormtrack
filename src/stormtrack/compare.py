"""Compare the IMD best-track record with IBTrACS (or any second track dataset).

Storms are paired by *track*, not by name or id: two storms match when they share
fixes at the same times and sit close together. Fix-by-fix differences in
position, wind and pressure are then summarised.

>>> import stormtrack as st
>>> cmp = st.compare_tracks(st.load(), st.load_ibtracs(basin="NI"))
>>> cmp.matches          # one row per paired storm
>>> cmp.summary()        # position / wind / pressure agreement

Wind speeds are not like-for-like: IMD reports 3-minute sustained wind, JTWC
(``ib_wind="usa"``) 1-minute, and WMO (Harper et al. 2010, WMO/TD-1555) provides no
3-min conversion — only 1-min <-> 10-min (:func:`stormtrack.analysis.convert_vmax`). So
no rescaling is applied by default; ``ib_wind_scale`` lets you apply your own.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .analysis import _obs, haversine_km

_IB_WIND = {"wmo": "wmo_wind", "usa": "usa_wind", "imd": "imd_wind", "merged": "wind"}
_IB_PRES = {"wmo": "wmo_pres", "usa": "usa_pres", "imd": "imd_pres", "merged": "pressure"}


@dataclass
class Comparison:
    """Result of :func:`compare_tracks`."""

    matches: pd.DataFrame  # one row per paired storm
    fixes: pd.DataFrame  # one row per fix present in both records
    unmatched_a: pd.DataFrame  # storms in the first dataset with no partner
    unmatched_b: pd.DataFrame  # storms in the second dataset with no partner

    def summary(self) -> pd.DataFrame:
        """Agreement statistics over all common fixes (second minus first dataset)."""
        f = self.fixes
        rows = []
        pe = f["pos_err_km"].dropna()
        rows.append(
            {"variable": "position (km)", "n": len(pe), "bias": np.nan, "mae": pe.mean(),
             "rmse": float(np.sqrt((pe**2).mean())) if len(pe) else np.nan,
             "median": pe.median(), "p90": pe.quantile(0.9), "corr": np.nan}
        )  # fmt: skip
        for var, label in (("wind", "wind (kt)"), ("pres", "pressure (hPa)")):
            both = f[[f"a_{var}", f"b_{var}"]].dropna()
            d = both[f"b_{var}"] - both[f"a_{var}"]
            rows.append(
                {"variable": label, "n": len(d), "bias": d.mean(), "mae": d.abs().mean(),
                 "rmse": float(np.sqrt((d**2).mean())) if len(d) else np.nan,
                 "median": d.median(), "p90": d.abs().quantile(0.9),
                 "corr": both[f"a_{var}"].corr(both[f"b_{var}"]) if len(d) > 2 else np.nan}
            )  # fmt: skip
        return pd.DataFrame(rows).set_index("variable")

    def __repr__(self) -> str:
        return (
            f"<Comparison: {len(self.matches)} matched storms, {len(self.fixes)} common fixes, "
            f"{len(self.unmatched_a)} unmatched in A, {len(self.unmatched_b)} in B>"
        )


def _prep_a(a: pd.DataFrame) -> pd.DataFrame:
    out = a[["storm_id", "time", "lat", "lon"]].copy()
    out["wind"] = a["wind"]
    out["pres"] = a["pressure"] if "pressure" in a else np.nan
    return out


def _prep_b(b: pd.DataFrame, wind: str, scale: float) -> pd.DataFrame:
    if wind not in _IB_WIND:
        raise ValueError(f"ib_wind must be one of {sorted(_IB_WIND)}")
    wcol = _IB_WIND[wind] if _IB_WIND[wind] in b else "wind"
    pcol = _IB_PRES[wind] if _IB_PRES[wind] in b else "pressure"
    out = b[["storm_id", "time", "lat", "lon"]].copy()
    out["wind"] = b[wcol] * scale
    out["pres"] = b[pcol] if pcol in b else np.nan
    return out


def compare_tracks(
    a,
    b,
    max_km: float = 300.0,
    min_common: int = 2,
    ib_wind: str = "usa",
    ib_wind_scale: float = 1.0,
) -> Comparison:
    """Pair storms between two datasets and compare their fixes.

    Parameters
    ----------
    a, b : :class:`~stormtrack.BestTracks` (or observations frames). ``a`` is the
           reference (normally the IMD record), ``b`` the other (IBTrACS).
    max_km : a pair must have mean separation below this over their common times.
    min_common : minimum number of common fix times for a pair to be considered.
    ib_wind : which of ``b``'s intensity columns to use — ``"usa"`` (JTWC, an
           independent estimate), ``"wmo"`` (the basin's WMO agency; for the North
           Indian Ocean that is IMD itself), ``"imd"`` (IMD's IBTrACS submission) or
           ``"merged"`` (``wind``: WMO else USA).
    ib_wind_scale : multiplier applied to ``b``'s wind (default 1; there is no
           WMO-recommended 1-min -> 3-min factor, see the module note).

    Each storm is paired with at most one partner (closest first).
    """
    ao, bo = _obs(a), _obs(b)
    A, B = _prep_a(ao), _prep_b(bo, ib_wind, ib_wind_scale)

    pad = max_km / 111.0 + 2.0  # only IBTrACS fixes near the IMD footprint can match
    B = B[
        B["lat"].between(A["lat"].min() - pad, A["lat"].max() + pad)
        & B["time"].between(A["time"].min(), A["time"].max())
    ]
    j = A.merge(B, on="time", suffixes=("_a", "_b"))
    j["pos_err_km"] = haversine_km(j["lat_a"], j["lon_a"], j["lat_b"], j["lon_b"])
    j = j[j["pos_err_km"] <= max_km * 2]  # drop clearly unrelated storms early

    pair = (
        j.groupby(["storm_id_a", "storm_id_b"])["pos_err_km"]
        .agg(n_common="size", mean_dist_km="mean")
        .reset_index()
    )
    pair = pair[(pair["n_common"] >= min_common) & (pair["mean_dist_km"] <= max_km)]
    pair = pair.sort_values(["mean_dist_km", "n_common"], ascending=[True, False])
    pair = pair.drop_duplicates("storm_id_a").drop_duplicates(
        "storm_id_b"
    )  # one-to-one, closest wins

    fixes = j.merge(pair[["storm_id_a", "storm_id_b"]], on=["storm_id_a", "storm_id_b"])
    fixes = fixes.rename(
        columns={"wind_a": "a_wind", "wind_b": "b_wind", "pres_a": "a_pres", "pres_b": "b_pres"}
    )
    fixes["d_wind"] = fixes["b_wind"] - fixes["a_wind"]
    fixes["d_pres"] = fixes["b_pres"] - fixes["a_pres"]
    fixes = fixes[
        ["storm_id_a", "storm_id_b", "time", "lat_a", "lon_a", "lat_b", "lon_b", "pos_err_km",
         "a_wind", "b_wind", "d_wind", "a_pres", "b_pres", "d_pres"]
    ].sort_values(["storm_id_a", "time"]).reset_index(drop=True)  # fmt: skip

    sa, sb = _storm_table(ao), _storm_table(bo)
    matches = (
        pair.merge(sa.add_suffix("_a"), left_on="storm_id_a", right_index=True)
        .merge(sb.add_suffix("_b"), left_on="storm_id_b", right_index=True)
        .reset_index(drop=True)
    )
    matches["d_peak_wind"] = matches["max_wind_b"] * ib_wind_scale - matches["max_wind_a"]
    matches["d_start_h"] = (matches["start_b"] - matches["start_a"]).dt.total_seconds() / 3600
    matches["d_end_h"] = (matches["end_b"] - matches["end_a"]).dt.total_seconds() / 3600
    # peak wind per fix selection of ``b`` may differ from the merged column; recompute
    peak_b = fixes.groupby("storm_id_b")["b_wind"].max()
    matches["peak_wind_b_common"] = matches["storm_id_b"].map(peak_b)

    return Comparison(
        matches=matches,
        fixes=fixes,
        unmatched_a=sa[~sa.index.isin(pair["storm_id_a"])].reset_index(),
        unmatched_b=_in_footprint(sb, A)[lambda s: ~s.index.isin(pair["storm_id_b"])].reset_index(),
    )


def _storm_table(obs: pd.DataFrame) -> pd.DataFrame:
    g = obs.groupby("storm_id", sort=False)
    return pd.DataFrame(
        {
            "name": g["name"].first() if "name" in obs else None,
            "start": g["time"].min(),
            "end": g["time"].max(),
            "max_wind": g["wind"].max(),
            "lat0": g["lat"].first(),
            "lon0": g["lon"].first(),
        }
    )


def _in_footprint(storms: pd.DataFrame, A: pd.DataFrame) -> pd.DataFrame:
    """Keep storms that begin inside the first dataset's lat/lon/time range, so
    'unmatched' doesn't list every cyclone on Earth when ``b`` is global."""
    return storms[
        storms["lat0"].between(A["lat"].min() - 5, A["lat"].max() + 5)
        & storms["lon0"].between(A["lon"].min() - 5, A["lon"].max() + 5)
        & storms["start"].between(A["time"].min(), A["time"].max())
    ]
