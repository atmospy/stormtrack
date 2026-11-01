"""Tests for the non-destructive position quality-control flag."""

import pandas as pd

from stormtrack import BestTracks
from stormtrack import _schema as S
from stormtrack.parse import _summarize_storms
from stormtrack.qc import flag_dates, flag_positions


def _track(coords, sid="2020-001"):
    t0 = pd.Timestamp("2020-05-16")
    return pd.DataFrame(
        {
            "storm_id": sid,
            "time": [t0 + pd.Timedelta(hours=3 * i) for i in range(len(coords))],
            "lat": [c[0] for c in coords],
            "lon": [c[1] for c in coords],
        }
    )


def test_flags_isolated_position_spike():
    # one bad middle fix jumps ~20° away and back
    obs = _track([(10, 80), (10.3, 80.2), (30, 60), (10.6, 80.6), (10.9, 80.8)])
    assert list(flag_positions(obs)) == [False, False, True, False, False]


def test_no_flag_on_a_normal_track():
    obs = _track([(10, 80), (10.3, 80.2), (10.6, 80.4), (10.9, 80.6)])
    assert not flag_positions(obs).any()


def test_short_track_never_flagged():
    obs = _track([(10, 80), (30, 60)])  # only 2 fixes -> no interior fix to bracket
    assert not flag_positions(obs).any()


def _bestracks_with_spike():
    obs = pd.DataFrame(
        {
            "storm_id": ["2020-001"] * 3,
            "year": [2020] * 3,
            "serial": [1] * 3,
            "name": [None] * 3,
            "basin": ["BOB"] * 3,
            "time": pd.to_datetime(["2020-05-16 00:00", "2020-05-16 03:00", "2020-05-16 06:00"]),
            "lat": [10.0, 30.0, 10.6],
            "lon": [80.0, 60.0, 80.4],
            "wind": [25.0, 25.0, 25.0],
            "pressure": [1000.0, 1000.0, 1000.0],
            "grade": pd.Categorical(["D", "D", "D"], categories=S.GRADE_ORDER, ordered=True),
            "step": [0, 1, 2],
            "pos_suspect": [False, True, False],
        }
    )
    return BestTracks(obs, pd.DataFrame(), _summarize_storms(obs))


def test_clean_drop_removes_flagged_fix():
    c = _bestracks_with_spike().clean(how="drop")
    assert len(c.observations) == 2
    assert not c.observations["pos_suspect"].any()
    assert list(c.observations["step"]) == [0, 1]  # renumbered


def test_clean_mask_nulls_position_but_keeps_row():
    m = _bestracks_with_spike().clean(how="mask")
    assert len(m.observations) == 3
    bad = m.observations[m.observations["pos_suspect"]]
    assert bad["lat"].isna().all() and bad["lon"].isna().all()


def _date_swap_track():
    # A storm running Apr 25-30 → May 1/2/3, but the May dates are stored
    # day/month-swapped as Jan/Feb/Mar 5 (the Nargis pattern). Good fixes are the
    # majority, as in real storms, so the median date is a stable reference.
    good = [f"2008-04-{d:02d} 00:00" for d in (25, 26, 27, 28, 29, 30)]
    swapped = ["2008-01-05 00:00", "2008-02-05 00:00", "2008-03-05 00:00"]  # really May 1/2/3
    return pd.DataFrame(
        {
            "storm_id": "2008-001",
            "time": pd.to_datetime(good + swapped),
            "lat": 14.0,
            "lon": 88.0,
        }
    )


def test_flag_dates_detects_day_month_swap():
    obs = _date_swap_track()
    suspect, corrected = flag_dates(obs)
    assert suspect.tolist() == [False] * 6 + [True, True, True]
    # the three swapped rows correct to May 1/2/3
    assert corrected[suspect].dt.month.tolist() == [5, 5, 5]
    assert corrected[suspect].dt.day.tolist() == [1, 2, 3]


def test_flag_dates_leaves_normal_track_alone():
    obs = pd.DataFrame(
        {
            "storm_id": "2020-001",
            "time": pd.to_datetime([f"2020-05-{d} 00:00" for d in (10, 11, 12, 13)]),
            "lat": 12.0,
            "lon": 88.0,
        }
    )
    suspect, _ = flag_dates(obs)
    assert not suspect.any()


def test_clean_fix_dates_reorders_chronologically():
    obs = _date_swap_track()
    obs["date_suspect"], _ = flag_dates(obs)
    obs["pos_suspect"] = False
    obs["step"] = range(len(obs))
    obs["year"] = 2008
    obs["serial"] = 1
    obs["name"] = "NARGIS"
    obs["basin"] = "BOB"
    obs["wind"] = 65.0
    obs["pressure"] = 980.0
    obs["grade"] = pd.Categorical(["VSCS"] * len(obs), categories=S.GRADE_ORDER, ordered=True)
    bt = BestTracks(obs, pd.DataFrame(), _summarize_storms(obs))

    fixed = bt.clean(fix_dates=True).observations
    # after correction the track runs Apr 25 → May 3, in order
    assert fixed["time"].is_monotonic_increasing
    assert fixed["time"].iloc[-1] == pd.Timestamp("2008-05-03")
    span_days = (fixed["time"].max() - fixed["time"].min()).days
    assert span_days == 8  # Apr 25 → May 3, not ~120


def test_resolve_dates_prefers_the_stored_reading_on_a_clean_track():
    from datetime import datetime

    from stormtrack.qc import resolve_dates

    dates = [datetime(2020, 5, 16)] * 3 + [datetime(2020, 5, 17)] * 2
    assert resolve_dates(dates, 2020) == dates


def test_resolve_dates_fixes_a_transposed_block():
    from datetime import datetime

    from stormtrack.qc import resolve_dates

    # 30 Apr, then 1-2 May written month-first as 5 Jan / 5 Feb
    dates = [datetime(2008, 4, 30), datetime(2008, 1, 5), datetime(2008, 2, 5)]
    assert resolve_dates(dates, 2008) == [
        datetime(2008, 4, 30),
        datetime(2008, 5, 1),
        datetime(2008, 5, 2),
    ]


def test_resolve_dates_gives_up_rather_than_guessing():
    from datetime import datetime

    from stormtrack.qc import resolve_dates

    # a date that recurs after another has intervened is not a simple keying
    # error, so the sequence is returned untouched
    dates = [datetime(2010, 6, 1), datetime(2010, 6, 2), datetime(2010, 6, 1)]
    assert resolve_dates(dates, 2010) == dates


def test_resolve_dates_handles_an_empty_track():
    from stormtrack.qc import resolve_dates

    assert resolve_dates([], 2020) == []


def test_resolve_dates_leaves_a_long_gap_alone():
    """Blocks more than MAX_BLOCK_GAP_DAYS apart admit no consistent reading,
    so the sequence is returned untouched rather than forced."""
    from datetime import datetime

    from stormtrack.qc import resolve_dates

    dates = [datetime(2011, 6, 1), datetime(2011, 7, 20)]
    assert resolve_dates(dates, 2011) == dates


def test_resolve_dates_ignores_an_impossible_year_snap():
    """29 February cannot be snapped into a non-leap sheet year; the candidate
    is skipped rather than raising."""
    from datetime import datetime

    from stormtrack.qc import resolve_dates

    dates = [datetime(2020, 2, 29), datetime(2020, 3, 1)]
    assert resolve_dates(dates, 2019) == dates


def test_flag_positions_without_the_required_columns():
    import pandas as pd

    from stormtrack.qc import flag_positions

    out = flag_positions(pd.DataFrame({"storm_id": ["a"], "time": [pd.Timestamp("2020-01-01")]}))
    assert not out.any()


def test_clean_fix_dates_falls_back_for_legacy_datasets():
    """Datasets published before ``time_resolved`` existed must still be
    correctable through the older median-based heuristic."""
    import pandas as pd

    from stormtrack.core import BestTracks
    from stormtrack.parse import _summarize_storms

    times = [pd.Timestamp("2008-04-30 00:00")] * 3 + [pd.Timestamp("2008-01-05 00:00")]
    obs = pd.DataFrame(
        {
            "storm_id": ["2008-001"] * 4,
            "year": [2008] * 4,
            "serial": [1] * 4,
            "basin": ["BOB"] * 4,
            "name": ["NARGIS"] * 4,
            "time": times,
            "pressure": [962.0] * 4,
            "lat": [16.0, 16.1, 16.2, 16.3],
            "lon": [92.0, 92.5, 93.0, 93.5],
            "wind": [65.0] * 4,
            "grade": ["VSCS"] * 4,
            "date_suspect": [False, False, False, True],
            "pos_suspect": [False] * 4,
            "step": [0, 1, 2, 3],
        }
    )
    bt = BestTracks(obs, pd.DataFrame(), _summarize_storms(obs), "0" * 64)
    out = bt.clean(fix_dates=True).observations
    assert "time_resolved" not in out.columns
    assert out["time"].max() == pd.Timestamp("2008-05-01 00:00")


def test_clean_fix_dates_uses_the_resolved_column(tmp_path):
    """The normal path: the parser resolved the calendar, so ``clean`` simply
    adopts ``time_resolved`` and re-orders the track."""
    from datetime import datetime

    import openpyxl

    from stormtrack.core import BestTracks
    from stormtrack.parse import parse_workbook

    header = [
        "Serial Number of system during year",
        "Basin of origin",
        "Name",
        "Date(DD-MM-YYYY)",
        "Time (UTC)",
        "Latitude (lat.)",
        "Longitude (lon.)",
        'CI No [or "T. No"]',
        "Estimated Central Pressure (hPa)",
        "Maximum Sustained Surface Wind (kt) ",
        "Pressure Drop (hPa)",
        "Grade (text)",
        "Outermost closed isobar (hPa)",
        "Diameter/Size of outermost closed isobar",
    ]

    def fix(date, time, lat, lon):
        return [1, "BOB", "NARGIS", date, time, lat, lon, 1.5, "990", "65", "20", "VSCS", "", ""]

    rows = [header]
    for hh in ("0000", "0600"):
        rows.append(fix(datetime(2008, 4, 30), hh, 16.0, 92.0))
    for month in (1, 2):  # 1 and 2 May, written the wrong way round
        rows.append(fix(datetime(2008, month, 5), "0000", 16.0, 94.0))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "2008"
    for r in rows:
        ws.append(r)
    path = tmp_path / "wb.xlsx"
    wb.save(path)

    frames = parse_workbook(path)
    bt = BestTracks(frames["observations"], frames["remarks"], frames["storms"], "0" * 64)
    assert bt.observations["date_suspect"].sum() == 2

    out = bt.clean(fix_dates=True).observations
    assert out["time"].tolist() == sorted(out["time"].tolist())
    assert out["time"].max() == pd.Timestamp("2008-05-02 00:00")
