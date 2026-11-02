"""Load the IBTrACS archive into the same tidy schema as the IMD record.

`IBTrACS <https://www.ncei.noaa.gov/products/international-best-track-archive>`_
merges the best tracks of every agency worldwide. :func:`load_ibtracs` returns a
:class:`~stormtrack.BestTracks` whose ``observations`` / ``storms`` frames use the
same column names as ``st.load()``, so every function in :mod:`stormtrack.analysis`
and :mod:`stormtrack.plot` works on either dataset.

Wind speeds are in knots, but **averaging periods differ by agency**: ``wmo_wind``
follows each basin's WMO agency in that agency's own convention (e.g. IMD 3-min,
JMA 10-min, NHC/CPHC 1-min), ``usa_wind`` is the JTWC/NHC 1-min sustained wind.
``wind`` is ``wmo_wind`` filled with ``usa_wind``; ``wind_agency`` records which one
each fix used.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from . import _repo
from . import _schema as S
from . import fetch as _fetch
from .core import BestTracks

PathLike = Union[str, Path]

IBTRACS_VERSION = "v04r01"
_BASE_URL = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-"
    "stewardship-ibtracs/{version}/access/csv/ibtracs.{code}.list.{version}.csv"
)
BASINS = ("NI", "WP", "EP", "NA", "SA", "SP", "SI")  # IBTrACS genesis-basin codes

_USECOLS = [
    "SID", "SEASON", "NUMBER", "BASIN", "SUBBASIN", "NAME", "ISO_TIME", "NATURE", "LAT",
    "LON", "WMO_WIND", "WMO_PRES", "WMO_AGENCY", "TRACK_TYPE", "DIST2LAND", "LANDFALL",
    "USA_LAT", "USA_LON", "USA_WIND", "USA_PRES", "USA_SSHS", "USA_RMW", "USA_ROCI",
    "STORM_SPEED",
    "NEWDELHI_GRADE", "NEWDELHI_WIND", "NEWDELHI_PRES", "NEWDELHI_LAT", "NEWDELHI_LON",
]  # fmt: skip


def ibtracs_url(basin: Optional[str] = None, version: str = IBTRACS_VERSION) -> str:
    """NCEI download URL for one basin's CSV (``None`` -> the global ``ALL`` file)."""
    code = "ALL" if basin is None else _check_basin(basin)
    return _BASE_URL.format(version=version, code=code)


def _check_basin(basin: str) -> str:
    b = str(basin).upper()
    if b not in BASINS:
        raise ValueError(f"unknown IBTrACS basin {basin!r}; expected one of {BASINS}")
    return b


def fetch_ibtracs(
    basin: Optional[str] = None,
    version: str = IBTRACS_VERSION,
    cache_dir: Optional[PathLike] = None,
    update: bool = False,
    timeout: float = 600.0,
) -> Path:
    """Download (once) and cache an IBTrACS CSV; returns the local path.

    ``basin=None`` fetches the global file (~330 MB); a basin code (``"NI"``, ...)
    fetches just that basin's file, which is far smaller.
    """
    cache = Path(cache_dir) if cache_dir else _fetch.default_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    code = "ALL" if basin is None else _check_basin(basin)
    dest = cache / f"ibtracs.{code}.list.{version}.csv"
    if dest.exists() and not update:
        return dest
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(ibtracs_url(basin, version), timeout=timeout) as r:  # noqa: S310
        with open(tmp, "wb") as fh:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                fh.write(chunk)
    tmp.replace(dest)
    return dest


def load_ibtracs(
    path: Optional[PathLike] = None,
    basin: Optional[str] = None,
    source: str = "github",
    since: Optional[int] = None,
    until: Optional[int] = None,
    main_only: bool = True,
    keep_nature: Optional[tuple] = None,
    version: str = IBTRACS_VERSION,
    cache_dir: Optional[PathLike] = None,
    update: bool = False,
) -> BestTracks:
    """Load IBTrACS as a :class:`~stormtrack.BestTracks` (``source="ibtracs"``).

    Parameters
    ----------
    path : a local IBTrACS ``.csv`` (any basin file or ``ALL``); overrides ``source``.
    basin : keep storms whose *genesis* basin is this code (``"NI"``, ``"WP"``, ...).
    source : where to read from when ``path`` is not given. ``"github"`` (default)
           loads the pre-parsed **North Indian Ocean** dataset published in this
           repo under ``data/ibtracs/`` — fast, no CSV parsing. ``"ncei"`` downloads
           the CSV from NOAA/NCEI (any ``basin``; ``None`` = the ~330 MB global file).
    since, until : inclusive season (year) bounds.
    main_only : keep **one track per storm** — its ``main`` track, or, for storms that have no
           ``main`` track yet (the newest seasons, still in IBTrACS' provisional state), their
           ``PROVISIONAL`` / ``US-PROVISIONAL`` track. ``spur`` duplicates are always dropped.
           The ``track_type`` column says which kind each fix is, so provisional winds (e.g. JTWC's,
           not yet reviewed) can be filtered out. ``False`` keeps every row.
    keep_nature : restrict to these ``NATURE`` codes, e.g. ``("TS",)``.

    The ``storm_id`` is the IBTrACS ``SID``; ``year`` the season; ``basin`` the
    storm's genesis basin (constant per storm, so tracks stay whole across basin
    lines). For North Indian storms ``grade`` holds IMD's own grade as submitted
    to IBTrACS, using the same ordered categories as ``st.load()``.
    """
    if source not in ("github", "ncei"):
        raise ValueError("source must be 'github' or 'ncei'")
    if path is None and source == "github":
        if basin not in (None, "NI"):
            raise ValueError(
                "the published dataset covers the North Indian Ocean (NI) only; "
                "use source='ncei' for other basins"
            )
        bt = _load_published(update=update, cache_dir=cache_dir)
        return _select(bt, since, until, keep_nature, main_only)
    if path is None:
        path = fetch_ibtracs(basin, version=version, cache_dir=cache_dir, update=update)
    df = _read_csv(Path(path))
    if main_only:
        df = df[_one_track(df["sid"], df["track_type"])]
    if keep_nature:
        df = df[df["nature"].isin(keep_nature)]
    obs = _tidy(df)
    if basin is not None:
        obs = obs[obs["basin"] == _check_basin(basin)]
    return _bundle(obs, since, until)


def _bundle(obs, since, until) -> BestTracks:
    if since is not None:
        obs = obs[obs["year"] >= since]
    if until is not None:
        obs = obs[obs["year"] <= until]
    obs = obs.sort_values(["storm_id", "time"], kind="stable").reset_index(drop=True)
    obs["step"] = obs.groupby("storm_id", sort=False).cumcount()
    return BestTracks(
        observations=obs,
        remarks=pd.DataFrame(columns=["storm_id", "remark"]),
        storms=summarize_storms(obs),
        sha256=None,
        source="ibtracs",
    )


_PROVISIONAL_TYPES = ("PROVISIONAL", "US-PROVISIONAL")


def _one_track(sid: pd.Series, track_type: pd.Series) -> pd.Series:
    """Boolean mask selecting one track per storm: ``main`` rows, or — for a storm with no
    ``main`` rows at all — its (US-)PROVISIONAL rows. Spur tracks never qualify.

    Filtering on ``main`` alone silently dropped whole storms that only exist as provisional
    tracks (e.g. 2025's Montha, Shakhti and Ditwah in the North Indian Ocean).
    """
    tt = track_type.astype(str)
    is_main = tt.str.startswith("main")
    has_main = is_main.groupby(sid).transform("any")
    return is_main | (~has_main & tt.isin(_PROVISIONAL_TYPES))


def _select(bt, since, until, keep_nature, main_only) -> BestTracks:
    """Apply the load filters to an already-tidy bundle (the published dataset)."""
    obs = bt.observations
    if main_only:
        obs = obs[_one_track(obs["storm_id"], obs["track_type"])]
    if keep_nature:
        obs = obs[obs["nature"].isin(keep_nature)]
    out = _bundle(obs.copy(), since, until)
    out.sha256 = bt.sha256
    return out


def _read_csv(path: Path) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0).columns
    cols = [c for c in _USECOLS if c in header]
    df = pd.read_csv(
        path,
        skiprows=[1],  # the units row
        usecols=cols,
        low_memory=False,
        keep_default_na=False,
        na_values=["", " "],
    )
    df.columns = [c.lower() for c in df.columns]
    return df


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["storm_id"] = df["sid"].astype(str)
    out["year"] = pd.to_numeric(df["season"], errors="coerce").astype("Int64").astype("int64")
    out["serial"] = pd.to_numeric(df.get("number"), errors="coerce").fillna(0).astype("int64")
    out["time"] = pd.to_datetime(df["iso_time"], errors="coerce")
    for c in ("lat", "lon"):
        out[c] = pd.to_numeric(df[c], errors="coerce")
    out["lon"] = (out["lon"] + 180) % 360 - 180  # one convention across the dateline
    # a storm keeps its genesis basin for its whole life
    out["basin"] = df["basin"].groupby(df["sid"]).transform("first").astype(str)
    # ...while ``obs_basin`` is the basin IBTrACS tags each observation with, so the part of a track
    # in a given basin (e.g. a western Pacific storm's North Indian tail) can still be told apart
    out["obs_basin"] = df["basin"].astype(str)
    out["subbasin"] = df.get("subbasin")
    name = df["name"].astype("string").str.strip().str.upper()
    out["name"] = name.where(~name.isin(["UNNAMED", "NOT_NAMED", ""]), None)
    out["nature"] = df.get("nature")
    out["track_type"] = df.get("track_type")

    # the JTWC/NHC (``usa_``) analysis position, kept apart from the default ``lat``/``lon`` so
    # the two can be compared; longitudes use the same dateline convention as ``lon``
    out["usa_lat"] = pd.to_numeric(df.get("usa_lat"), errors="coerce")
    out["usa_lon"] = (pd.to_numeric(df.get("usa_lon"), errors="coerce") + 180) % 360 - 180

    for src, dst in (
        ("wmo_wind", "wmo_wind"),
        ("usa_wind", "usa_wind"),
        ("wmo_pres", "wmo_pres"),
        ("usa_pres", "usa_pres"),
    ):
        out[dst] = pd.to_numeric(df.get(src), errors="coerce")
    out["wind"] = out["wmo_wind"].fillna(out["usa_wind"])
    out["wind_agency"] = np.where(
        out["wmo_wind"].notna(), "wmo", np.where(out["usa_wind"].notna(), "usa", None)
    )
    out["pressure"] = out["wmo_pres"].fillna(out["usa_pres"])
    out["sshs"] = pd.to_numeric(df.get("usa_sshs"), errors="coerce")
    for c in ("dist2land", "storm_speed", "usa_rmw", "usa_roci"):
        out[c] = pd.to_numeric(df.get(c), errors="coerce")
    out["landfall"] = pd.to_numeric(df.get("landfall"), errors="coerce")

    # IMD's own submission (North Indian Ocean only)
    out["grade"] = pd.Categorical(
        df.get("newdelhi_grade", pd.Series(index=df.index, dtype=object)).map(_grade),
        categories=S.GRADE_ORDER,
        ordered=True,
    )
    for c in ("wind", "pres", "lat", "lon"):
        out[f"imd_{c}"] = pd.to_numeric(df.get(f"newdelhi_{c}"), errors="coerce")
    return out.dropna(subset=["time", "lat", "lon"])


def _grade(v):
    """IBTrACS spells some IMD grades differently, e.g. ``SCS(H)``; fold to ours."""
    return None if v is None or v != v else S.normalize_grade(str(v).split("(")[0])


def summarize_storms(obs: pd.DataFrame) -> pd.DataFrame:
    """One row per storm: id, name, genesis basin, span, peak wind/pressure/grade."""
    cols = [
        "storm_id", "year", "serial", "name", "basin", "start_time", "end_time", "n_obs",
        "peak_grade", "max_wind", "min_pressure", "lat0", "lon0",
    ]  # fmt: skip
    if obs.empty:
        return pd.DataFrame(columns=cols)
    g = obs.groupby("storm_id", sort=False)
    s = g.agg(
        year=("year", "first"),
        serial=("serial", "first"),
        name=("name", "first"),
        basin=("basin", "first"),
        start_time=("time", "min"),
        end_time=("time", "max"),
        n_obs=("time", "size"),
        max_wind=("wind", "max"),
        min_pressure=("pressure", "min"),
        lat0=("lat", "first"),
        lon0=("lon", "first"),
    ).reset_index()
    s["peak_grade"] = g["grade"].max().to_numpy() if "grade" in obs else None
    return s[cols]


# --------------------------------------------------------------------------- #
# Published dataset: the North Indian Ocean subset committed under data/ibtracs/
# --------------------------------------------------------------------------- #

PUBLISHED_DIR = "ibtracs"  # sub-directory of the repo's data/ folder
PUBLISHED_BASIN = "NI"
_FRAMES = ("observations", "storms")


@dataclass
class IbtracsManifest:
    format: int
    source_url: str
    source_sha256: str
    version: str
    basin: str
    generated_at: str
    n_storms: int
    n_obs: int
    year_min: Optional[int]
    year_max: Optional[int]


def _read_manifest(d: Path) -> Optional[IbtracsManifest]:
    try:
        raw = json.loads((Path(d) / "manifest.json").read_text())
        return IbtracsManifest(**{f: raw.get(f) for f in IbtracsManifest.__dataclass_fields__})
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _read_published_dir(d: Path) -> BestTracks:
    d = Path(d)
    obs = pd.read_parquet(d / "observations.parquet")
    obs["grade"] = pd.Categorical(obs["grade"], categories=S.GRADE_ORDER, ordered=True)
    m = _read_manifest(d)
    return BestTracks(
        observations=obs,
        remarks=pd.DataFrame(columns=["storm_id", "remark"]),
        storms=pd.read_parquet(d / "storms.parquet"),
        sha256=m.source_sha256 if m else None,
        source="ibtracs",
    )


def _load_published(update: bool, cache_dir: Optional[PathLike]) -> BestTracks:
    """Read the published NI dataset: ``$STORMTRACK_DATA_DIR/ibtracs`` if set, else
    the parquet files cached from the GitHub repo (re-fetched when ``update``)."""
    local = _repo.env("DATA_DIR")
    if local:
        return _read_published_dir(Path(local) / PUBLISHED_DIR)
    cache = Path(cache_dir) if cache_dir else _fetch.default_cache_dir()
    d = cache / "repo_data" / PUBLISHED_DIR
    d.mkdir(parents=True, exist_ok=True)
    for fn in ("observations.parquet", "storms.parquet", "manifest.json"):
        _fetch._download_if_changed(
            _repo.raw_url(f"{PUBLISHED_DIR}/{fn}"), d / fn, d / f"{fn}.meta.json",
            update=update, timeout=120.0,
        )  # fmt: skip
    return _read_published_dir(d)


def _validate_published(bt: BestTracks) -> None:
    obs = bt.observations
    problems = []
    if len(bt.storms) < 1500:
        problems.append(f"only {len(bt.storms)} storms (expected >= 1500 for NI)")
    if obs.duplicated(["storm_id", "time"]).any():
        problems.append("duplicate (storm_id, time) fixes")
    if not (obs["lat"].between(-90, 90).all() and obs["lon"].between(-180, 180).all()):
        problems.append("coordinates out of range")
    if obs["wind"].dropna().gt(250).any() or obs["wind"].dropna().lt(0).any():
        problems.append("implausible wind speeds")
    if (obs["basin"] != PUBLISHED_BASIN).any():
        problems.append("non-NI storms in the NI file")
    if problems:
        raise ValueError("IBTrACS validation failed: " + "; ".join(problems))


def build_ibtracs(
    data_dir: PathLike,
    version: str = IBTRACS_VERSION,
    force: bool = False,
    cache_dir: Optional[PathLike] = None,
) -> tuple:
    """Fetch the NCEI North Indian Ocean CSV and publish it into ``data_dir/ibtracs/``.

    Mirrors :func:`stormtrack.build`: a content hash is compared with the published
    manifest, unchanged sources are skipped, and the new data is validated before
    the parquet files are (atomically) replaced. Returns ``(changed, manifest)``.
    """
    out = Path(data_dir) / PUBLISHED_DIR
    cache = Path(cache_dir) if cache_dir else _fetch.default_cache_dir()
    csv = fetch_ibtracs(PUBLISHED_BASIN, version=version, cache_dir=cache, update=True)
    sha = _fetch._sha256(csv)
    prev = _read_manifest(out)
    if (
        not force
        and prev
        and prev.source_sha256 == sha
        and all((out / f"{n}.parquet").exists() for n in _FRAMES)
    ):
        return False, prev

    bt = load_ibtracs(path=csv, basin=PUBLISHED_BASIN)
    _validate_published(bt)
    out.mkdir(parents=True, exist_ok=True)
    frames = {"observations": bt.observations, "storms": bt.storms}
    for name, df in frames.items():
        dst = out / f"{name}.parquet"
        tmp = dst.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        os.replace(tmp, dst)
    obs = bt.observations
    m = IbtracsManifest(
        format=1,
        source_url=ibtracs_url(PUBLISHED_BASIN, version),
        source_sha256=sha,
        version=version,
        basin=PUBLISHED_BASIN,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        n_storms=int(len(bt.storms)),
        n_obs=int(len(obs)),
        year_min=int(obs["year"].min()),
        year_max=int(obs["year"].max()),
    )
    tmp = out / "manifest.json.tmp"
    tmp.write_text(json.dumps(asdict(m), indent=2) + "\n")
    os.replace(tmp, out / "manifest.json")
    return True, m
