"""Regression tests for the parser, built on small synthetic workbooks.

These lock in the tricky real-world behaviours: forward-filled serials, name
bleed between storms, free-text remark rows, messy numeric cells, and the
alternate 16-column (split-date) sheet layout.
"""

from datetime import datetime

import openpyxl
import pytest

from imdtrack import _schema as S
from imdtrack.parse import parse_workbook

HEADER_14 = [
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

HEADER_16 = [
    "Serial Number of system during year",
    "Basin of origin",
    "Name",
    "Date(DD/MM/YYYY)",
    "Time (UTC)",
    "Latitude (lat)",
    "longitude  (Long)",
    'CI No [or "T. No"]',
    "Estimated Central Pressure (hPa)",
    "Maximum Sustained Surface Wind (kt) ",
    "Pressure Drop (hPa)",
    "Grade (text)",
    "Outermost closed isobar (hPa)",
    "DD",
    "MM",
    "YYYY",
]


def _write(tmp_path, sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    path = tmp_path / "wb.xlsx"
    wb.save(path)
    return path


@pytest.mark.parametrize(
    "lat_raw,lon_raw,expected",
    [
        ("8.5/96.5", "8.5/96.5", (8.5, 96.5)),  # packed in both cells (2013 LEHAR)
        ("12.0", "88.0", (12.0, 88.0)),  # normal separate cells
        ("10.0/95.0", None, (10.0, 95.0)),  # packed only in the lat cell
    ],
)
def test_parse_latlon(lat_raw, lon_raw, expected):
    assert S.parse_latlon(lat_raw, lon_raw) == expected


def test_latlon_pair_string_is_split(tmp_path):
    """Some rows pack 'lat/lon' into one string in both coordinate cells; without
    splitting, lon wrongly equals lat (2013 LEHAR/MADI tracked at ~8°E instead
    of ~96°E)."""
    rows = [
        HEADER_14,
        [
            9,
            "BOB",
            "LEHAR",
            datetime(2013, 11, 23),
            "1200",
            "8.5/96.5",
            "8.5/96.5",
            1.5,
            "1004",
            "25",
            "3",
            "D",
            "",
            "",
        ],
        [
            None,
            "BOB",
            "LEHAR",
            None,
            "1800",
            "9.0/96.0",
            "9.0/96.0",
            2,
            "1002",
            "30",
            "5",
            "DD",
            "",
            "",
        ],
    ]
    res = parse_workbook(_write(tmp_path, {"2013": rows}))
    o = res["observations"]
    assert len(o) == 2
    assert o["lat"].iloc[0] == 8.5 and o["lon"].iloc[0] == 96.5
    assert o["lon"].iloc[1] == 96.0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("16-06-2008", datetime(2008, 6, 16)),
        ("01/10/2025", datetime(2025, 10, 1)),
        ("24.5.2021", datetime(2021, 5, 24)),
        (datetime(2020, 5, 16, 3, 0), datetime(2020, 5, 16)),
        ("garbage", None),
        (None, None),
    ],
)
def test_parse_date(raw, expected):
    assert S.parse_date(raw) == expected


def test_text_string_dates_are_parsed(tmp_path):
    """Some storms store the date as day-first text ("16-06-2008") rather than a
    datetime; without parsing it, every fix in the storm is dropped."""
    rows = [
        HEADER_14,
        [3, "BOB", None, "16-06-2008", "0300", 21.5, 90.0, 1.5, "990", "30", "5", "DD", "", ""],
        [None, "BOB", None, None, "0900", 21.5, 89.5, 1.5, "990", "30", "5", "DD", "", ""],
        [None, "BOB", None, "17-06-2008", "0300", 23.0, 88.5, 1.5, "992", "25", "3", "D", "", ""],
    ]
    res = parse_workbook(_write(tmp_path, {"2008": rows}))
    obs = res["observations"]
    assert len(obs) == 3
    assert obs["time"].iloc[0] == datetime(2008, 6, 16, 3, 0)
    assert obs["time"].iloc[2] == datetime(2008, 6, 17, 3, 0)


def test_per_basin_serial_does_not_merge_storms(tmp_path):
    """IMD restarts the serial number per basin in older years (ARB 1,2 then
    BOB 1,2). Keying storms on (year, serial) would merge ARB #1 with BOB #1;
    each must stay a separate storm with a unique id."""
    d1, d2 = datetime(1993, 11, 12), datetime(1993, 12, 1)
    rows = [
        HEADER_14,
        [1, "ARB", None, d1, "0300", 15.0, 68.0, 1.5, "1000", "25", "3", "D", "", ""],
        [
            2,
            "ARB",
            None,
            datetime(1993, 11, 8),
            "0300",
            12.0,
            66.0,
            1.5,
            "1000",
            "25",
            "3",
            "D",
            "",
            "",
        ],
        [],  # blank separator between basins
        [1, "BOB", None, d2, "0600", 12.0, 88.0, 2.0, "990", "90", "42", "ESCS", "", ""],
        [
            2,
            "BOB",
            None,
            datetime(1993, 12, 19),
            "0000",
            14.0,
            90.0,
            1.5,
            "998",
            "30",
            "5",
            "DD",
            "",
            "",
        ],
    ]
    res = parse_workbook(_write(tmp_path, {"1993": rows}))
    storms = res["storms"]
    assert len(storms) == 4  # not 2 — ARB #1/#2 and BOB #1/#2 are distinct
    assert storms["storm_id"].tolist() == ["1993-001", "1993-002", "1993-003", "1993-004"]
    by_id = storms.set_index("storm_id")
    assert by_id.loc["1993-001", "basin"] == "ARB"
    assert by_id.loc["1993-003", "basin"] == "BOB"
    assert by_id.loc["1993-003", "peak_grade"] == "ESCS"


def test_merged_date_cell_is_forward_filled(tmp_path):
    """The Date column is a merged cell: it is populated only on the first row of
    each day and ``None`` on the 3-hourly rows below. All those fixes must still
    be captured (regression for dropping ~7/8 of every storm's track)."""
    day1 = datetime(2021, 5, 14)
    day2 = datetime(2021, 5, 15)
    rows = [
        HEADER_14,
        # Serial + date only on the first row of the storm/day (merged-cell effect)
        [2, "AS", "TAUKTAE", day1, "0300", 10.5, 72.3, 1.5, "997", "25", "3", "D", "", ""],
        [None, "AS", "TAUKTAE", None, "0600", 11.0, 72.5, 1.5, "996", "25", "4", "D", "", ""],
        [None, "AS", "TAUKTAE", None, "0900", 11.5, 72.5, 2.0, "995", "30", "5", "D", "", ""],
        [None, "AS", "TAUKTAE", None, "1200", 11.6, 72.6, 2.0, "995", "30", "6", "DD", "", ""],
        # Next day: date reappears on its first row, then None again
        [None, "AS", "TAUKTAE", day2, "0000", 12.7, 72.5, 2.5, "992", "40", "8", "CS", "", ""],
        [None, "AS", "TAUKTAE", None, "0300", 12.8, 72.5, 2.5, "992", "40", "8", "CS", "", ""],
    ]
    res = parse_workbook(_write(tmp_path, {"2021": rows}))
    obs = res["observations"]
    assert len(obs) == 6  # not 2 — the merged-date continuation rows are kept
    assert obs["storm_id"].nunique() == 1
    assert list(obs["step"]) == [0, 1, 2, 3, 4, 5]
    # times are reconstructed from the forward-filled date + each row's HHMM
    assert obs["time"].iloc[1] == datetime(2021, 5, 14, 6, 0)
    assert obs["time"].iloc[5] == datetime(2021, 5, 15, 3, 0)


def test_serial_ffill_and_grouping(tmp_path):
    d = datetime(2020, 5, 16)
    rows = [
        HEADER_14,
        [1, "BOB", "AMPHAN", d, "0000", 10.4, 87.0, 1.5, "1000", "25", "3", "D", "", ""],
        [None, "BOB", "AMPHAN", d, "0300", 10.7, 86.5, 1.5, "1000", "25", "3", "D", "", ""],
        [None, "BOB", "AMPHAN", d, "0600", 10.9, 86.3, 2.0, "998", "30", "5", "DD", "", ""],
    ]
    res = parse_workbook(_write(tmp_path, {"2020": rows}))
    obs = res["observations"]
    assert len(obs) == 3
    assert obs["storm_id"].nunique() == 1
    assert obs["storm_id"].iloc[0] == "2020-001"
    assert list(obs["step"]) == [0, 1, 2]
    assert obs["name"].unique().tolist() == ["AMPHAN"]


def test_name_does_not_bleed_across_storms(tmp_path):
    d = datetime(2020, 5, 16)
    rows = [
        HEADER_14,
        [1, "BOB", "AMPHAN", d, "0000", 10.4, 87.0, 1.5, "1000", "25", "3", "D", "", ""],
        [None, "BOB", "AMPHAN", d, "0300", 10.7, 86.5, 1.5, "1000", "25", "3", "D", "", ""],
        [],  # blank separator
        [
            2,
            "ARB",
            None,
            datetime(2020, 5, 29),
            "0900",
            15.0,
            68.0,
            1.5,
            "1000",
            "25",
            "3",
            "D",
            "",
            "",
        ],
    ]
    res = parse_workbook(_write(tmp_path, {"2020": rows}))
    storms = res["storms"].set_index("storm_id")
    assert storms.loc["2020-001", "name"] == "AMPHAN"
    assert storms.loc["2020-002", "name"] is None or storms.loc["2020-002", "name"] != "AMPHAN"


def test_remark_rows_captured_not_dropped(tmp_path):
    d = datetime(2020, 5, 20)
    remark = "Crossed West Bengal coast near Sagar Island around 1000 UTC."
    rows = [
        HEADER_14,
        [1, "BOB", "AMPHAN", d, "0900", 21.4, 88.1, 5.0, "960", "90", "42", "ESCS", "", ""],
        [None, "BOB", "AMPHAN", d, remark, None, None, None, None, None, None, None, "", ""],
        [None, "BOB", "AMPHAN", d, "1200", 21.9, 88.4, "-", "957", "85", "36", "VSCS", "", ""],
    ]
    res = parse_workbook(_write(tmp_path, {"2020": rows}))
    assert len(res["observations"]) == 2  # remark row is not a track fix
    assert len(res["remarks"]) == 1
    assert remark in res["remarks"]["remark"].iloc[0]
    assert res["remarks"]["storm_id"].iloc[0] == "2020-001"


def test_messy_numeric_and_time_coercion(tmp_path):
    d = datetime(1992, 6, 17)
    rows = [
        HEADER_14,
        # time '0' -> 00:00, ECP as float, wind as str, pressure_drop '-' -> NaN
        [2, "BOB", None, d, 0, "19.0", 89.0, "-", 992, "30", "-", "D", "994", "5.0"],
    ]
    res = parse_workbook(_write(tmp_path, {"1992": rows}))
    o = res["observations"].iloc[0]
    assert o["time"] == datetime(1992, 6, 17, 0, 0)
    assert o["lat"] == 19.0 and o["pressure"] == 992.0 and o["wind"] == 30.0
    assert o["ci_no"] != o["ci_no"]  # '-' -> NaN


def test_16_column_split_date_layout(tmp_path):
    d = datetime(2025, 5, 24)
    rows = [
        HEADER_16,
        [1, "AS", None, d, "0000", 17.0, 73.0, 1.5, 998, 25, 3, "D", None, 24, 5, 2025],
        [None, "AS", None, d, "0300", 17.0, 73.2, 1.5, 998, 25, 3, "D", None, 24, 5, 2025],
    ]
    res = parse_workbook(_write(tmp_path, {"2025": rows}))
    obs = res["observations"]
    assert len(obs) == 2
    assert obs["basin"].iloc[0] == "ARB"  # "AS" normalized to ARB
    assert obs["oci_diameter"].isna().all()  # no diameter col in this layout
    assert obs["time"].iloc[1] == datetime(2025, 5, 24, 3, 0)


def test_note_row_above_header(tmp_path):
    rows = [
        ["The best track parameters are tentative and subject to finalisation."],
        HEADER_16,
        [
            1,
            "BOB",
            None,
            datetime(2026, 1, 7),
            "0300",
            4.8,
            88.2,
            1.5,
            1008,
            25,
            3,
            "D",
            None,
            7,
            1,
            2026,
        ],
    ]
    res = parse_workbook(_write(tmp_path, {"2026": rows}))
    assert len(res["observations"]) == 1


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("BOB", "BOB"),
        ("AS", "ARB"),
        ("arb", "ARB"),
        ("Land", "LAND"),
        ("junk", None),
    ],
)
def test_basin_normalization(raw, expected):
    assert S.normalize_basin(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("NIVAR’", "NIVAR"),
        ("-", None),
        ("--", None),
        ("SYSTEM CROSSED COAST NEAR X", None),
        ("AMPHAN", "AMPHAN"),
    ],
)
def test_name_normalization(raw, expected):
    assert S.normalize_name(raw) == expected


def test_grade_is_ordered_category(tmp_path):
    d = datetime(2020, 5, 16)
    rows = [
        HEADER_14,
        [1, "BOB", "X", d, "0000", 10.0, 87.0, 1.5, "1000", "25", "3", "D", "", ""],
        [None, "BOB", "X", d, "0300", 10.0, 87.0, 6.5, "920", "130", "84", "SuCS", "", ""],
    ]
    res = parse_workbook(_write(tmp_path, {"2020": rows}))
    grade = res["observations"]["grade"]
    assert grade.cat.ordered
    assert grade.max() == "SuCS"
    assert res["storms"]["peak_grade"].iloc[0] == "SuCS"


def _fix(serial, basin, name, date, time, lat, lon, grade="D", wind="25"):
    return [serial, basin, name, date, time, lat, lon, 1.5, "1000", wind, "3", grade, "", ""]


def test_blank_row_inside_a_storm_does_not_split_it(tmp_path):
    """A stray blank row occurs *within* a storm's block (2001, BOB serial 2).
    Blank rows usually separate storms, but one must not start a new storm when
    the (serial, basin) key is unchanged — that reported one system as two."""
    d1, d2 = datetime(2001, 6, 12), datetime(2001, 6, 13)
    rows = [
        HEADER_14,
        _fix(2, "BOB", None, d1, "0300", 19.5, 87.0),
        [],  # stray blank *inside* the block
        _fix(2, "BOB", None, d1, "1200", 20.0, 86.5),
        _fix(2, "BOB", None, d2, "0300", 21.0, 85.5),
    ]
    res = parse_workbook(_write(tmp_path, {"2001": rows}))
    assert res["storms"]["storm_id"].tolist() == ["2001-001"]
    assert len(res["observations"]) == 3


def test_single_row_serial_typo_does_not_split_a_storm(tmp_path):
    """One row of FANOOS (2005) carries serial 10 in an otherwise serial-11
    block. A serial that covers a single mid-block row and then reverts is a
    keying error, not a storm boundary — it once produced three storms."""
    d = datetime(2005, 12, 10)
    rows = [
        HEADER_14,
        _fix(11, "BOB", "FANOOS", d, "0000", 10.5, 80.5, "CS", "45"),
        _fix(10, "BOB", "FANOOS", d, "0300", 10.4, 79.8, "DD", "30"),  # typo
        _fix(11, "BOB", "FANOOS", d, "0600", 10.5, 79.5),
        _fix(11, "BOB", "FANOOS", d, "0900", 10.5, 79.5),
    ]
    res = parse_workbook(_write(tmp_path, {"2005": rows}))
    storms = res["storms"]
    assert storms["storm_id"].tolist() == ["2005-001"]
    assert storms["serial"].iloc[0] == 11
    assert len(res["observations"]) == 4


def test_day_month_transposed_dates_are_resolved(tmp_path):
    """Nargis (2008): 1-3 May were stored month-first as 5 Jan/Feb/Mar, so the
    storm appeared to span four months. ``time`` keeps the workbook value and
    ``time_resolved`` carries the corrected one."""
    rows = [HEADER_14]
    for hh in ("0000", "0600", "1200", "1800"):
        rows.append(_fix(1, "BOB", "NARGIS", datetime(2008, 4, 30), hh, 16.0, 92.0))
    for month in (1, 2, 3):  # 1, 2, 3 May written the wrong way round
        for hh in ("0000", "0600"):
            rows.append(_fix(1, "BOB", "NARGIS", datetime(2008, month, 5), hh, 16.0, 94.0))

    obs = parse_workbook(_write(tmp_path, {"2008": rows}))["observations"]
    assert len(obs) == 10
    assert obs["date_suspect"].sum() == 6
    resolved = obs.sort_values("time_resolved")["time_resolved"]
    assert resolved.min() == datetime(2008, 4, 30)
    assert resolved.max() == datetime(2008, 5, 3, 6)
    # the track is a continuous six-day event once resolved
    assert (resolved.max() - resolved.min()).days == 3


def test_mis_keyed_year_is_resolved_from_the_sheet(tmp_path):
    """1988-002 carries a 1989 date on one row of a June 1988 storm."""
    rows = [
        HEADER_14,
        _fix(2, "BOB", None, datetime(1988, 6, 9), "0300", 19.0, 89.0),
        _fix(2, "BOB", None, datetime(1988, 6, 10), "0300", 19.5, 88.5),
        _fix(2, "BOB", None, datetime(1989, 6, 12), "0300", 20.0, 88.0),  # 1989 typo
    ]
    obs = parse_workbook(_write(tmp_path, {"1988": rows}))["observations"]
    assert obs["date_suspect"].sum() == 1
    assert obs["time_resolved"].max() == datetime(1988, 6, 12, 3)


def test_storm_crossing_new_year_is_left_alone(tmp_path):
    """A December storm running into January legitimately carries the next
    year, and must not be 'corrected' back into its own sheet year."""
    rows = [
        HEADER_14,
        _fix(7, "BOB", None, datetime(2017, 12, 30), "0600", 8.0, 92.0),
        _fix(7, "BOB", None, datetime(2017, 12, 31), "0600", 8.5, 91.0),
        _fix(7, "BOB", None, datetime(2018, 1, 1), "0600", 9.0, 90.0),
    ]
    obs = parse_workbook(_write(tmp_path, {"2017": rows}))["observations"]
    assert not obs["date_suspect"].any()
    assert obs["time_resolved"].tolist() == obs["time"].tolist()


def test_fix_with_one_missing_coordinate_is_kept(tmp_path):
    """Some rows carry a real time, pressure, wind and grade but only one
    coordinate — the cell is blank or reads "Over land" once the system is
    inland (1982 #10, 2008 RASHMI, 2017 #7). Those are observations with an
    incomplete position, not remarks, and must not be discarded."""
    d = datetime(2017, 10, 20)
    rows = [
        HEADER_14,
        _fix(7, "BOB", None, d, "0000", 20.8, 86.0),
        [7, "BOB", None, d, "0300", 21.0, None, "-", 998, 25, 4, "D", "", ""],
        [7, "BOB", None, d, "0600", 21.5, "Over land", "-", 998, 25, 4, "D", "", ""],
        [7, "BOB", None, d, "0900", None, 85.0, "-", 998, 25, 4, "D", "", ""],
    ]
    obs = parse_workbook(_write(tmp_path, {"2017": rows}))["observations"]
    assert len(obs) == 4
    assert obs["lon"].isna().sum() == 2
    assert obs["lat"].isna().sum() == 1
    assert obs["wind"].notna().all()  # the intensity data is what makes them fixes


def test_row_without_intensity_or_position_is_not_a_fix(tmp_path):
    """The relaxed position rule must not turn remark rows into observations."""
    d = datetime(2020, 5, 20)
    remark = "Crossed West Bengal coast near Sagar Island around 1000 UTC."
    rows = [
        HEADER_14,
        _fix(1, "BOB", "AMPHAN", d, "0900", 21.4, 88.1),
        [1, "BOB", "AMPHAN", d, "1200", remark, None, None, None, None, None, None, "", ""],
        [1, "BOB", "AMPHAN", d, "1500", 21.9, None, None, None, None, None, None, "", ""],
    ]
    res = parse_workbook(_write(tmp_path, {"2020": rows}))
    assert len(res["observations"]) == 1  # neither trailing row is a fix
    assert len(res["remarks"]) == 1


def test_counter_matches_the_parser_exactly(tmp_path):
    """``count_positional_rows`` is the completeness guard: it must count the
    same rows the parser emits, so a shortfall or surplus is a real bug."""
    from imdtrack.parse import count_positional_rows

    d = datetime(2013, 11, 11)
    rows = [
        HEADER_14,
        _fix(1, "BOB", "LEHAR", d, "0000", "8.5/96.5", "8.5/96.5"),  # packed pair
        [1, "BOB", "LEHAR", d, "0300", 8.6, None, "-", 998, 25, 4, "D", "", ""],
        [
            1,
            "BOB",
            "LEHAR",
            d,
            "0600",
            "not a position",
            None,
            None,
            None,
            None,
            None,
            None,
            "",
            "",
        ],
        _fix(1, "BOB", "LEHAR", d, "0900", 8.8, 96.0),
    ]
    path = _write(tmp_path, {"2013": rows})
    obs = parse_workbook(path)["observations"]
    assert sum(count_positional_rows(path).values()) == len(obs) == 3


def test_non_numeric_serial_is_ignored(tmp_path):
    """A serial cell that is not a number must not start or end a storm."""
    d = datetime(2019, 11, 9)
    rows = [
        HEADER_14,
        _fix(1, "BOB", "BULBUL", d, "0000", 15.0, 88.0),
        _fix("n/a", "BOB", "BULBUL", d, "0300", 15.2, 88.2),
        _fix(1, "BOB", "BULBUL", d, "0600", 15.4, 88.4),
    ]
    res = parse_workbook(_write(tmp_path, {"2019": rows}))
    assert res["storms"]["storm_id"].tolist() == ["2019-001"]
    assert len(res["observations"]) == 3


def test_count_positional_rows_skips_a_sheet_without_a_header(tmp_path):
    from imdtrack.parse import count_positional_rows

    d = datetime(2020, 5, 16)
    good = [HEADER_14, _fix(1, "BOB", "AMPHAN", d, "0000", 10.4, 87.0)]
    headerless = [["just", "a", "note"], [None, None, None]]
    path = _write(tmp_path, {"2020": good, "2021": headerless})
    counts = count_positional_rows(path)
    assert counts.get(2020) == 1
    assert counts.get(2021, 0) == 0
