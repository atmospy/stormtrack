"""imdtrack - IMD RSMC New Delhi cyclone best-track data as pandas / xarray.

Quick start
-----------
>>> import imdtrack as imd
>>> bt = imd.load()                 # download the pre-parsed dataset from GitHub
>>> df = bt.observations            # tidy pandas DataFrame, one row per fix
>>> ds = bt.to_xarray()             # (storm, step) xarray.Dataset
>>> bt = imd.load(update=True)      # re-fetch only if the repo published new data
>>> ib = imd.load_ibtracs()          # IBTrACS North Indian Ocean, same schema
>>> imd.compare_tracks(bt, ib)      # IMD vs IBTrACS, storm by storm

The published dataset is rebuilt from the IMD workbook by a scheduled GitHub
Action (see :mod:`imdtrack.pipeline`); ``load(source="imd")`` parses the raw
workbook directly instead.
"""

from __future__ import annotations

from . import analysis, atcf, realtime, verification
from ._schema import GRADE_LONG, GRADE_ORDER, VALID_BASINS
from .compare import Comparison, compare_tracks
from .core import BestTracks, load, update
from .fetch import DEFAULT_URL, fetch_data_from_repo, fetch_workbook
from .ibtracs import build_ibtracs, fetch_ibtracs, load_ibtracs
from .parse import parse_workbook
from .pipeline import build
from .plot import plot_forecast, plot_track, plot_tracks
from .qc import flag_positions

__all__ = [
    "load",
    "update",
    "build",
    "build_ibtracs",
    "load_ibtracs",
    "fetch_ibtracs",
    "compare_tracks",
    "Comparison",
    "analysis",
    "BestTracks",
    "parse_workbook",
    "fetch_workbook",
    "fetch_data_from_repo",
    "flag_positions",
    "plot_track",
    "plot_tracks",
    "plot_forecast",
    "atcf",
    "realtime",
    "verification",
    "DEFAULT_URL",
    "GRADE_ORDER",
    "GRADE_LONG",
    "VALID_BASINS",
]

try:  # version is written by hatch-vcs at build time, from the git tag
    from ._version import __version__
except ImportError:  # pragma: no cover  (source checkout without a build)
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("imdtrack")
    except PackageNotFoundError:
        __version__ = "0.0.0+unknown"
