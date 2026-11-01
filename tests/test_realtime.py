"""ATCF parsing, real-time fetchers (mocked), forecast verification and the cone."""

import gzip

import numpy as np
import pandas as pd
import pytest

import imdtrack as imd
from imdtrack import analysis as A
from imdtrack import realtime as R
from imdtrack import verification as V
from imdtrack.atcf import best_track_frame, parse_atcf

# Layout copied from real NHC files: 28+ comma-separated fields, wind radii on repeated lines.
FST = """\
AL, 04, 2026082812, 03, OFCL,   0, 148N,  458W,  35,    0, DB,  34, NEQ,  100,    0,    0,   80,    0,    0,   0,  45,   0,    ,   0, JLB, 285,  21,           ,  ,
AL, 04, 2026082812, 03, OFCL,  12, 156N,  503W,  35,    0, PT,  34, NEQ,  100,    0,    0,   80,    0,    0,   0,  45,   0,    ,   0, JLB, 280,  22,
AL, 04, 2026082812, 03, OFCL,  12, 156N,  503W,  35,    0, PT,  50, NEQ,   40,    0,    0,   30,    0,    0,   0,  45,   0,    ,   0, JLB, 280,  22,
AL, 04, 2026082812, 03, OFCL,  24, 164N,  547W,  50,    0, TS,  34, NEQ,   90,    0,    0,   70,    0,    0,   0,  45,   0,    ,   0, JLB, 280,  22,
AL, 04, 2026082812, 03, OFCL,  48, 180N,  620W,  70,    0, HU,  34, NEQ,   90,    0,    0,   70,    0,    0,   0,  45,   0,    ,   0, JLB, 280,  22,
"""
BEST = """\
IO, 04, 2026110100,   , BEST,   0, 116N, 0866E,  35, 1007, XX,  34, NEQ,   30,    0,    0,    0, 1011,  110,  25,   0,   0,   B,   0,   X, 295,  12,       FOUR, M,
IO, 04, 2026110106,   , BEST,   0, 122N, 0848E,  40, 1003, XX,  34, NEQ,   35,    0,    0,   30, 1012,  140,  20,   0,   0,   B,   0,   X, 295,  14,       FOUR, M,
"""


def test_parse_atcf_fields_and_radii():
    d = parse_atcf(FST)
    assert len(d) == 4  # 5 lines, tau 12 repeated for the 50-kt radii
    r = d.set_index("tau")
    assert r.loc[0, "lat"] == pytest.approx(14.8) and r.loc[0, "lon"] == pytest.approx(
        -45.8
    )  # tenths, W negative
    assert r.loc[0, "atcf_id"] == "AL042026" and r.loc[12, "ty"] == "PT"
    assert np.isnan(r.loc[0, "mslp"]) and np.isnan(parse_atcf(FST).loc[0, "mslp"])  # 0 -> NaN
    assert r.loc[12, "r34_ne"] == 100 and r.loc[12, "r50_ne"] == 40  # merged onto one row
    assert r.loc[24, "time"] - r.loc[24, "init"] == pd.Timedelta(hours=24)


def test_parse_wraps_longitude_and_skips_junk():
    txt = "WP, 01, 2026010100, 03, JTWC, 0, 100N, 1795E, 40, 990, TS\nnot a line\n\n"
    d = parse_atcf(txt.encode())
    assert len(d) == 1 and d["lon"].iloc[0] == pytest.approx(179.5)
    e = parse_atcf("WP, 01, 2026010100, 03, JTWC, 0, 100N, 1805E, 40, 990, TS")
    assert e["lon"].iloc[0] == pytest.approx(-179.5)
    assert parse_atcf("").empty
    # implausible values become NaN
    bad = parse_atcf("AL, 01, 2026010100, 03, BEST, 0, 100N, 500W, 400, 2000, TS")
    assert bad[["vmax", "mslp"]].isna().all(axis=None)


def test_best_track_frame_schema_and_names():
    obs = best_track_frame(parse_atcf(BEST))
    assert obs["storm_id"].tolist() == ["IO042026"] * 2
    assert obs["basin"].iloc[0] == "NI" and obs["atcf_basin"].iloc[0] == "IO"
    assert obs["name"].isna().all()  # "FOUR" is a number word, not a name
    assert obs["wind"].tolist() == [35, 40] and obs["step"].tolist() == [0, 1]
    assert best_track_frame(parse_atcf(FST)).empty  # no BEST rows


def test_active_storms_filters_by_age_basin_and_invests(monkeypatch):
    listing = (
        b'<a href="bio042026.dat">x</a><a href="bio912026.dat">x</a><a href="bio032026.dat">x</a>'
    )
    old = BEST.replace("IO, 04", "IO, 03").replace("20261101", "20260101")

    def fake(url, timeout=60.0):
        if url.endswith("/"):
            return listing
        return {"bio042026.dat": BEST.encode(), "bio032026.dat": old.encode(),
                "bio912026.dat": BEST.replace("IO, 04", "IO, 91").encode()}[url.rsplit("/", 1)[1]]  # fmt: skip

    monkeypatch.setattr(R, "_get", fake)
    bt = R.active_storms("jtwc", basins=["io"], now="2026-11-01 12:00")
    assert bt.source == "atcf-jtwc" and list(bt.storms["storm_id"]) == ["IO042026"]
    assert (
        len(R.active_storms("jtwc", basins=["io"], invests=True, now="2026-11-01 12:00").storms)
        == 2
    )
    assert R.active_storms("jtwc", basins=["wp"], now="2026-11-01 12:00").storms.empty
    with pytest.raises(ValueError):
        R.active_storms("imd")


def test_get_forecast_and_guidance(monkeypatch):
    seen = []

    def fake(url, timeout=60.0):
        seen.append(url)
        if url.endswith(".gz"):
            return gzip.decompress(gzip.compress(FST.encode()))
        return FST.encode()

    monkeypatch.setattr(R, "_get", fake)
    fc = R.get_forecast("AL042026")
    assert seen[-1].endswith("/fst/al042026.fst") and (fc["tech"] == "OFCL").all()
    gd = R.get_guidance("AL042026", techs=["ofcl"])
    assert seen[-1].endswith("/aid_public/aal042026.dat.gz") and len(gd) == 4
    with pytest.raises(LookupError, match="no JTWC"):
        R.get_forecast("AL042026", source="jtwc", url="http://x/y.fst")
    with pytest.raises(ValueError):
        R.get_guidance("IO042026", source="jtwc")


def test_interpolate_forecast_is_time_linear_and_dateline_safe():
    fc = parse_atcf(
        "WP, 01, 2026010100, 03, JTWC, 0, 100N, 1790E, 40, 990, TS\n"
        "WP, 01, 2026010100, 03, JTWC, 12, 100N, 1810E, 60, 970, TY\n"
    )
    out = R.interpolate_forecast(fc, step=6)
    assert out["tau"].tolist() == [0, 6, 12]
    assert out["lon"].iloc[1] == pytest.approx(180.0) or out["lon"].iloc[1] == pytest.approx(-180.0)
    assert out["vmax"].tolist() == [40, 50, 60] and out["ty"].tolist() == ["TS", "TS", "TY"]
    assert A.ace(out.assign(storm_id="x", wind=out["vmax"]), synoptic_only=False)["ace"].iloc[0] > 0


def _track(lat0=10.0, lon0=87.0, n=9, dlat=0.0, dlon=-0.5, sid="2020-001"):
    t = pd.date_range("2020-05-16", periods=n, freq="6h")
    return pd.DataFrame({"storm_id": sid, "time": t, "lat": lat0 + dlat * np.arange(n),
                         "lon": lon0 + dlon * np.arange(n), "wind": np.linspace(30, 70, n),
                         "pressure": np.linspace(1000, 960, n), "ty": "TS"})  # fmt: skip


def test_forecast_errors_known_offsets_and_cross_source():
    best = _track()  # moving due west
    f = _track().iloc[[0, 2, 4]].copy()
    f = f.rename(columns={"wind": "vmax", "pressure": "mslp"})
    f["init"], f["tau"], f["tech"], f["atcf_id"] = (
        f["time"].iloc[0],
        [0, 12, 24],
        "OFCL",
        "IO012020",
    )
    f["f"] = 0
    f = f.rename(columns={})
    # forecast 0.5 deg north of the best track at every lead -> pure cross-track error
    f["lat"] += 0.5
    f["vmax"] += 5
    e = V.forecast_errors(f, best)  # single-storm best: ids may differ (IMD best vs ATCF id)
    assert len(e) == 3
    assert e["track_err_km"].between(55, 56).all()
    # heading is west, forecast is north => to the right of motion
    assert (e["cross_km"] > 50).all() and e["along_km"].abs().max() < 1
    assert e["vmax_err"].tolist() == [5, 5, 5]
    s = V.error_summary(e)
    assert s.loc[s.tau == 24, "track_mean_km"].iloc[0] == pytest.approx(55.6, abs=0.3)
    r = V.error_radii(e, pct=67, min_n=1, units="nm")
    assert r.loc[24] == pytest.approx(55.6 / 1.852, abs=0.3)
    assert V.error_radii(e, min_n=5).empty


def test_forecast_errors_respect_tc_only_and_gaps():
    best = _track()
    best.loc[best.index[4:], "ty"] = "LO"  # post-tropical from 24 h on
    f = pd.DataFrame({"atcf_id": "IO012020", "tech": "OFCL", "init": best["time"].iloc[0],
                      "tau": [0, 24, 48], "ty": "TS", "lat": 10.0, "lon": [87, 85.0, 83.0],
                      "vmax": 40.0, "mslp": np.nan})  # fmt: skip
    f["time"] = f["init"] + pd.to_timedelta(f["tau"], unit="h")
    assert V.forecast_errors(f, best)["tau"].tolist() == [0]  # LO at 24 h and 48 h dropped
    assert len(V.forecast_errors(f, best, tc_only=False)) == 3
    sparse = best.iloc[[0, 8]]  # 48 h gap between fixes
    assert V.forecast_errors(f, sparse, tc_only=False)["tau"].tolist() == [
        0,
        48,
    ]  # 24 h not interpolated


def _inside(poly, x, y):
    """Ray-casting point-in-polygon (keeps the test free of matplotlib)."""
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def test_cone_polygons_contain_the_forecast_points():
    fc = parse_atcf(
        "IO, 01, 2020051600, 03, JTWC, 0, 100N, 0870E, 40, 990, TS\n"
        "IO, 01, 2020051600, 03, JTWC, 24, 120N, 0850E, 60, 970, TY\n"
        "IO, 01, 2020051600, 03, JTWC, 48, 140N, 0830E, 80, 950, TY\n"
    )
    polys = V.cone_polygons(fc, {24: 80.0, 48: 150.0})
    assert len(polys) == 2
    assert _inside(polys[1], 83.0, 14.0) and _inside(polys[0], 85.0, 12.0)
    assert not _inside(polys[0], 88.5, 10.0)
    assert V.cone_polygons(fc.iloc[:1], {24: 80.0}) == []


def test_convert_vmax_and_grade_from_wind():
    assert A.convert_vmax(100.0) == pytest.approx(93.0)
    assert A.convert_vmax(93.0, 600, 60) == pytest.approx(100.0)
    assert A.convert_vmax(100.0, exposure="in-land") == pytest.approx(84.0)
    with pytest.raises(ValueError, match="Table 1.2"):
        A.convert_vmax(100.0, src_period=60, dst_period=180)  # no 3-min factor exists
    g = A.grade_from_wind([10, 17, 27, 28, 34, 48, 64, 90, 119, 120, np.nan])
    assert [None if x != x else x for x in g] == [
        None,
        "D",
        "D",
        "DD",
        "CS",
        "SCS",
        "VSCS",
        "ESCS",
        "ESCS",
        "SuCS",
        None,
    ]
    assert g.ordered


def test_plot_forecast_smoke():
    pytest.importorskip("cartopy")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fc = parse_atcf(FST)
    ax = imd.plot_forecast(fc, best=_track(14.0, -45.0, dlon=-0.1), radii_km={12: 50, 48: 200})
    assert ax is not None
    plt.close("all")


def test_plot_category_scales():
    pytest.importorskip("cartopy")
    from imdtrack.plot import _category

    ss = [c for c, _ in _category([20, 34, 63, 64, 83, 96, 113, 137, np.nan], "saffir-simpson")]
    assert ss == ["TD", "TS", "TS", "C1", "C2", "C3", "C4", "C5", None]
    imd_ = [c for c, _ in _category([10, 30, 55, 90, 120], "imd")]
    assert imd_ == [None, "DD", "SCS", "ESCS", "SuCS"]
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fc = parse_atcf(FST)
    for scale in ("saffir-simpson", "imd"):
        labels = [t.get_text() for t in imd.plot_forecast(fc, scale=scale).texts]
        assert any("kt" in t for t in labels)
    plt.close("all")


def test_plot_forecast_dateline_and_edge_cases():
    pytest.importorskip("cartopy")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    row = "WP, 01, 2026010100, 03, JTWC, {t}, {la}N, {lo}E, {w}, 990, TY"
    dl = parse_atcf(
        "\n".join(
            row.format(t=t, la=la, lo=lo, w=w)
            for t, la, lo, w in [(0, 100, 1780, 40), (24, 115, 1795, 60), (48, 130, 1810, 80)]
        )
    )
    ax = imd.plot_forecast(dl, radii_km={24: 50, 48: 90})
    x0, x1, _, _ = ax.get_extent(ax.projection)
    assert x1 - x0 < 40  # a regional map, not the whole globe
    assert ax.projection.proj4_params["lon_0"] == 180  # centred on the dateline
    # no wind anywhere, and a single point, must still draw
    nowind = dl.assign(vmax=np.nan)
    assert imd.plot_forecast(nowind) is not None
    assert imd.plot_forecast(dl.iloc[:1]) is not None
    plt.close("all")
