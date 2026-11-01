"""Tests for the end-user load paths that don't hit the network.

`st.load()` normally downloads the published dataset from GitHub. Setting
``STORMTRACK_DATA_DIR`` makes it read a local committed dataset instead — the same
mechanism the docs build and offline users rely on. These tests exercise that
path end to end without any HTTP.
"""

from datetime import datetime

import openpyxl
import pytest

import stormtrack as st
from stormtrack import store
from stormtrack.parse import parse_workbook

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


def _write_dataset(tmp_path):
    d = datetime(2020, 5, 16)
    rows = [
        HEADER_14,
        [1, "BOB", "AMPHAN", d, "0000", 10.4, 87.0, 1.5, "1000", "25", "3", "D", "", ""],
        [None, "BOB", "AMPHAN", d, "0300", 10.7, 86.5, 2.0, "998", "30", "5", "DD", "", ""],
        [None, "BOB", "AMPHAN", d, "0600", 11.0, 86.0, 6.5, "920", "130", "84", "SuCS", "", ""],
    ]
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(title="2020")
    for row in rows:
        ws.append(row)
    xlsx = tmp_path / "wb.xlsx"
    wb.save(xlsx)

    frames = parse_workbook(xlsx)
    data_dir = tmp_path / "data"
    store.write_dataset(frames, data_dir, source_url="http://x", source_sha256="deadbeef")
    return data_dir


def test_load_from_local_data_dir(tmp_path, monkeypatch):
    data_dir = _write_dataset(tmp_path)
    monkeypatch.setenv("STORMTRACK_DATA_DIR", str(data_dir))
    # Point the cache elsewhere so nothing leaks in from a real user cache.
    monkeypatch.setenv("STORMTRACK_CACHE", str(tmp_path / "cache"))

    bt = st.load()  # default source="github", but STORMTRACK_DATA_DIR short-circuits it

    assert len(bt.storms) == 1
    assert bt.storms["storm_id"].iloc[0] == "2020-001"
    assert bt.sha256 == "deadbeef"
    # ordered categorical restored on read
    assert bt.observations["grade"].cat.ordered
    assert bt.storm("2020-001")["wind"].max() == 130.0


def test_storm_lookup_by_id_and_name(tmp_path, monkeypatch):
    data_dir = _write_dataset(tmp_path)  # one storm, 2020-001, named AMPHAN
    monkeypatch.setenv("STORMTRACK_DATA_DIR", str(data_dir))
    monkeypatch.setenv("STORMTRACK_CACHE", str(tmp_path / "cache"))
    bt = st.load()

    by_id = bt.storm("2020-001")
    by_name = bt.storm("amphan")  # case-insensitive name lookup
    assert len(by_id) == len(by_name) == 3
    assert by_name["storm_id"].iloc[0] == "2020-001"

    with pytest.raises(KeyError):
        bt.storm("no-such-storm")


def test_load_local_to_xarray(tmp_path, monkeypatch):
    data_dir = _write_dataset(tmp_path)
    monkeypatch.setenv("STORMTRACK_DATA_DIR", str(data_dir))
    monkeypatch.setenv("STORMTRACK_CACHE", str(tmp_path / "cache"))

    ds = st.load().to_xarray()
    assert dict(ds.sizes) == {"storm": 1, "step": 3}
    assert float(ds.sel(storm="2020-001")["wind"].max()) == 130.0


def test_legacy_imdtrack_env_vars_still_work(tmp_path, monkeypatch):
    """The pre-rename IMDTRACK_* variables keep working; STORMTRACK_* takes precedence."""
    data_dir = _write_dataset(tmp_path)
    monkeypatch.delenv("STORMTRACK_DATA_DIR", raising=False)
    monkeypatch.setenv("IMDTRACK_DATA_DIR", str(data_dir))
    assert len(st.load().storms) == 1
    monkeypatch.setenv(
        "STORMTRACK_DATA_DIR", str(tmp_path / "nowhere")
    )  # wins over the legacy name
    with pytest.raises(FileNotFoundError):
        st.load()
