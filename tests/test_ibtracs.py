"""IBTrACS loading, the published-dataset pipeline, analysis and IMD comparison (offline)."""

import numpy as np
import pandas as pd
import pytest

import stormtrack as st
from stormtrack import analysis as A
from stormtrack import ibtracs as ib

COLS = [
    "SID", "SEASON", "NUMBER", "BASIN", "SUBBASIN", "NAME", "ISO_TIME", "NATURE", "LAT", "LON",
    "WMO_WIND", "WMO_PRES", "WMO_AGENCY", "TRACK_TYPE", "DIST2LAND", "LANDFALL", "USA_WIND",
    "USA_PRES", "USA_SSHS", "STORM_SPEED", "NEWDELHI_GRADE", "NEWDELHI_WIND", "NEWDELHI_PRES",
    "NEWDELHI_LAT", "NEWDELHI_LON",
]  # fmt: skip


def _storm(sid, name, t0, winds, lat0=10.0, lon0=87.0, basin="NI", track="main", usa_off=5):
    rows = []
    for i, w in enumerate(winds):
        t = pd.Timestamp(t0) + pd.Timedelta(hours=3 * i)
        grade = "DD" if w >= 30 else "D"
        rows.append([
            sid, t.year, 1, basin, "BB", name, t.strftime("%Y-%m-%d %H:%M:%S"), "TS",
            lat0 + 0.3 * i, lon0 - 0.2 * i, w, 1000 - w, "newdelhi", track, 100, 100,
            w + usa_off, 990, 0, 8, grade, w, 1000 - w, lat0 + 0.3 * i, lon0 - 0.2 * i,
        ])  # fmt: skip
    return rows


def _csv(tmp_path, rows):
    p = tmp_path / "ibtracs.NI.list.v04r01.csv"
    units = [" "] * len(COLS)
    df = pd.DataFrame([units] + rows, columns=COLS)
    df.to_csv(p, index=False)
    return p


@pytest.fixture
def csv(tmp_path):
    rows = (
        _storm("2020136N10087", "AMPHAN", "2020-05-16 00:00", [25, 30, 45, 80, 130, 140, 100])
        + _storm("2020137N10087", "UNNAMED", "2020-05-17 00:00", [25, 25, 30])
        + _storm("2020138N10087", "SPUR", "2020-05-18 00:00", [25, 25], track="spur-merge")
        + _storm("2020200N12150", "NOISE", "2020-07-18 00:00", [35, 40, 50], 12, 150, basin="WP")
    )
    return _csv(tmp_path, rows)


def test_load_csv_tidy_schema(csv):
    bt = st.load_ibtracs(path=csv)
    assert bt.source == "ibtracs" and "[ibtracs]" in repr(bt)
    obs = bt.observations
    assert {"storm_id", "year", "basin", "name", "time", "lat", "lon", "wind", "pressure",
            "grade", "step"} <= set(obs.columns)  # fmt: skip
    assert "2020138N10087" not in set(obs["storm_id"])  # spur track dropped
    assert obs["grade"].cat.ordered
    assert pd.isna(bt.storms.set_index("storm_id").loc["2020137N10087", "name"])  # UNNAMED
    assert bt.storms.set_index("storm_id").loc["2020136N10087", "max_wind"] == 140


def test_basin_year_filters(csv):
    assert set(st.load_ibtracs(path=csv, basin="NI").storms["basin"]) == {"NI"}
    assert st.load_ibtracs(path=csv, since=2021).observations.empty
    assert st.load_ibtracs(path=csv, until=2019).observations.empty
    with pytest.raises(ValueError):
        st.load_ibtracs(path=csv, basin="XX")


def test_wind_falls_back_to_usa(tmp_path):
    rows = _storm("2020136N10087", "A", "2020-05-16 00:00", [30, 40])
    df = pd.DataFrame([[" "] * len(COLS)] + rows, columns=COLS)
    df.loc[1, "WMO_WIND"] = np.nan  # first real row has no WMO wind
    p = tmp_path / "x.csv"
    df.to_csv(p, index=False)
    obs = st.load_ibtracs(path=p).observations
    assert obs["wind"].tolist() == [35.0, 40.0]  # USA = wmo + 5 when WMO missing
    assert obs["wind_agency"].tolist() == ["usa", "wmo"]


def test_build_publish_and_load_roundtrip(csv, tmp_path, monkeypatch):
    monkeypatch.setattr(ib, "fetch_ibtracs", lambda *a, **k: csv)
    monkeypatch.setattr(ib, "_validate_published", lambda bt: None)  # tiny fixture
    data = tmp_path / "data"
    changed, m = ib.build_ibtracs(data)
    assert changed and m.n_storms == 2  # AMPHAN + UNNAMED (spur dropped, WP excluded)
    assert (data / "ibtracs" / "observations.parquet").exists()
    changed2, _ = ib.build_ibtracs(data)
    assert not changed2  # same content hash -> no rewrite
    assert ib.build_ibtracs(data, force=True)[0]

    monkeypatch.setenv("STORMTRACK_DATA_DIR", str(data))
    bt = st.load_ibtracs()
    assert bt.source == "ibtracs" and bt.observations["grade"].cat.ordered
    assert bt.sha256 == m.source_sha256
    with pytest.raises(ValueError):
        st.load_ibtracs(basin="WP")


def test_validation_rejects_bad_data(csv):
    bt = st.load_ibtracs(path=csv, basin="NI")
    with pytest.raises(ValueError, match="storms"):
        ib._validate_published(bt)  # fixture has far fewer than 1500 storms


def test_to_xarray_ibtracs(csv):
    pytest.importorskip("xarray")
    ds = st.load_ibtracs(path=csv).to_xarray()
    assert "usa_wind" in ds and "IBTrACS" in ds.attrs["title"]


def _obs(winds, hours=6, sid="s"):
    t = pd.date_range("2020-01-01", periods=len(winds), freq=f"{hours}h")
    return pd.DataFrame(
        {
            "storm_id": sid,
            "time": t,
            "lat": 10.0,
            "lon": 80.0 + np.arange(len(winds)),
            "wind": winds,
            "year": 2020,
            "basin": "NI",
            "name": "X",
        }
    )


def test_rapid_intensification_uses_time_not_rows():
    ri = A.rapid_intensification(_obs([30, 40, 55, 70, 75]))  # +30 kt over 24 h (4 fixes)
    assert ri.loc[0, "max_dwind"] == 45 and ri.loc[0, "rapid"]
    no = A.rapid_intensification(_obs([30, 32, 35, 38, 40]))
    assert not no.loc[0, "rapid"]
    three_hourly = A.rapid_intensification(_obs([30] * 4 + [70] * 5, hours=3), hours=12)
    assert three_hourly.loc[0, "max_dwind"] == 40


def test_lifetime_max_counts_ace():
    o = pd.concat([_obs([20, 40, 70, 50], sid="a"), _obs([20, 35], sid="b").assign(year=2021)])
    lm = A.lifetime_max(o).set_index("storm_id")
    assert lm.loc["a", "lmi_wind"] == 70 and lm.loc["a", "duration_days"] == 0.75
    c = A.annual_counts(o).set_index("year")
    assert c.loc[2020, "hurricane"] == 1 and c.loc[2021, "tropical_storm"] == 1
    ace = A.ace(o).set_index("storm_id")["ace"]
    assert ace["a"] == pytest.approx((40**2 + 70**2 + 50**2) * 1e-4)
    assert A.monthly_climatology(o)["storms"].sum() == 2


def test_translation_speed_and_haversine():
    assert A.haversine_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.1)
    assert A.haversine_km(0, 179.5, 0, -179.5) == pytest.approx(111.19, abs=0.1)  # dateline
    sp = A.translation_speed(_obs([30, 30, 30]))
    assert sp["speed_kmh"].iloc[1] == pytest.approx(111.19 / 6 * 1.0, rel=0.02)
    assert sp["heading"].iloc[1] == pytest.approx(90, abs=1)  # due east


def test_match_controls_and_windows_and_bootstrap():
    ev = pd.DataFrame({"basin": ["NI"], "year": [2000], "peak_wind": [100.0]}, index=["e"])
    pool = pd.DataFrame(
        {"basin": ["NI", "NI", "WP", "NI"], "year": [1990, 2002, 2000, 2001],
         "peak_wind": [100.0, 95.0, 100.0, 140.0]},
        index=["far", "near", "wrong_basin", "too_strong"],
    )  # fmt: skip
    m = A.match_controls(ev, pool)
    assert m["control"].tolist() == ["near"]
    st = pd.DataFrame({"storm_id": ["a"], "start_time": [pd.Timestamp("2020-01-10")],
                       "end_time": [pd.Timestamp("2020-01-12")]})  # fmt: skip
    w = A.storm_windows(st, pad_days=1)
    assert set(w["phase"]) == {"pre", "during", "post"}
    assert w.loc[w["phase"] == "pre", "day"].min() == pytest.approx(-1.0)
    r = A.paired_bootstrap([3, 4, 5, 6], [1, 1, 1, 1])
    assert r["mean_diff"] == 3.5 and r["lo"] <= 3.5 <= r["hi"] and r["n"] == 4
    assert A.paired_bootstrap([1], [1])["n"] == 1


def test_compare_tracks_pairs_by_track(csv):
    ibt = st.load_ibtracs(path=csv)
    t = pd.date_range("2020-05-16", periods=7, freq="3h")
    imd_obs = pd.DataFrame({
        "storm_id": "2020-001", "name": "AMPHAN", "time": t,
        "lat": [10.0 + 0.3 * i + 0.05 for i in range(7)],
        "lon": [87.0 - 0.2 * i for i in range(7)],
        "wind": [25, 30, 45, 80, 130, 140, 100], "pressure": [975.0] * 7,
    })  # fmt: skip
    bt = st.BestTracks(imd_obs, pd.DataFrame(), pd.DataFrame())
    c = st.compare_tracks(bt, ibt)
    assert len(c.matches) == 1 and c.matches["storm_id_b"].iloc[0] == "2020136N10087"
    assert c.fixes["pos_err_km"].max() < 10
    s = c.summary()
    assert s.loc["wind (kt)", "bias"] == pytest.approx(5.0)  # JTWC fixture = IMD + 5
    assert st.compare_tracks(bt, ibt, ib_wind="wmo").summary().loc["wind (kt)", "bias"] == 0
    scaled = st.compare_tracks(bt, ibt, ib_wind_scale=0.0).summary()
    assert scaled.loc["wind (kt)", "bias"] < 0
    with pytest.raises(ValueError):
        st.compare_tracks(bt, ibt, ib_wind="nope")
    assert "1 matched" in repr(c)
