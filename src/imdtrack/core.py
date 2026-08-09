"""High-level entry points: fetch + parse + cache, exposed as pandas / xarray."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from . import fetch as _fetch
from . import parse as _parse
from .fetch import DEFAULT_URL

PathLike = Union[str, Path]


@dataclass
class BestTracks:
    """A parsed snapshot of the IMD best-track record.

    Attributes
    ----------
    observations : one tidy row per 3-hourly fix (the main table).
    remarks      : free-text landfall / weakening notes, linked by ``storm_id``.
    storms       : one summary row per storm.
    sha256       : content hash of the workbook these frames came from.
    """

    observations: pd.DataFrame
    remarks: pd.DataFrame
    storms: pd.DataFrame
    sha256: Optional[str] = None

    def to_dataframe(self) -> pd.DataFrame:
        """Return the tidy observations frame (alias for ``.observations``)."""
        return self.observations

    def to_xarray(self):
        """Return a 2-D ``(storm, step)`` :class:`xarray.Dataset`."""
        from .dataset import to_xarray

        return to_xarray(self.observations, self.storms)

    def storm(self, key: str) -> pd.DataFrame:
        """Track for a single storm, by ``storm_id`` (``"2021-002"``) or name
        (case-insensitive, e.g. ``"tauktae"``), sorted by time."""
        obs = self.observations
        sel = obs[obs["storm_id"] == key]
        if len(sel):
            return sel.sort_values("time")
        sel = obs[obs["name"].astype("string").str.upper() == str(key).strip().upper()]
        if len(sel):
            return sel.sort_values(["storm_id", "time"])
        raise KeyError(f"no storm with id or name {key!r}")

    def clean(self, how: str = "drop", fix_dates: bool = False) -> BestTracks:
        """Return a copy with QC-flagged errors handled (source never altered).

        ``pos_suspect`` marks fixes whose coordinates imply an impossible jump;
        ``date_suspect`` marks day/month-transposed dates. Both are source
        data-entry errors.

        how : how to treat ``pos_suspect`` fixes — ``"drop"`` removes them (and
              renumbers ``step``); ``"mask"`` keeps the rows but nulls
              ``lat``/``lon``.
        fix_dates : if True, correct ``date_suspect`` fixes by swapping day and
              month, then re-sort each track chronologically.
        """
        if how not in ("drop", "mask"):
            raise ValueError("how must be 'drop' or 'mask'")

        obs = self.observations.copy()
        changed = False

        if fix_dates and "date_suspect" in obs.columns and obs["date_suspect"].any():
            if "time_resolved" in obs.columns:
                # Resolved at parse time, where the workbook row order is known.
                obs["time"] = obs["time_resolved"]
            else:  # datasets published before time_resolved existed
                from .qc import flag_dates

                suspect, corrected = flag_dates(obs)
                obs.loc[suspect, "time"] = corrected[suspect]
            obs = obs.sort_values(["storm_id", "time"], kind="stable").reset_index(drop=True)
            obs["step"] = obs.groupby("storm_id", sort=False).cumcount()
            changed = True

        if "pos_suspect" in obs.columns and obs["pos_suspect"].any():
            if how == "drop":
                obs = obs[~obs["pos_suspect"]].reset_index(drop=True)
                obs["step"] = obs.groupby("storm_id", sort=False).cumcount()
            else:  # mask
                import numpy as np

                obs.loc[obs["pos_suspect"], ["lat", "lon"]] = np.nan
            changed = True

        if not changed:
            return BestTracks(obs, self.remarks.copy(), self.storms.copy(), self.sha256)

        from .parse import _summarize_storms

        return BestTracks(obs, self.remarks.copy(), _summarize_storms(obs), self.sha256)

    def __repr__(self) -> str:
        n_obs = len(self.observations)
        n_storm = len(self.storms)
        yrs = ""
        if n_storm:
            yrs = f", {int(self.storms['year'].min())}-{int(self.storms['year'].max())}"
        return f"<BestTracks: {n_storm} storms, {n_obs} fixes{yrs}>"


def _parquet_paths(cache_dir: Path):
    return {name: cache_dir / f"{name}.parquet" for name in ("observations", "remarks", "storms")}


def load(
    update: bool = False,
    source: str = "github",
    url: str = DEFAULT_URL,
    path: Optional[PathLike] = None,
    cache_dir: Optional[PathLike] = None,
    force: bool = False,
) -> BestTracks:
    """Load the best-track record as a :class:`BestTracks` bundle.

    Parameters
    ----------
    update : if True, check the source for a newer copy and re-download when it
             has changed (a cheap conditional GET, so it's a no-op when current).
    source : where the data comes from.  ``"github"`` (default) downloads the
             pre-parsed dataset published in the project's GitHub repo — no IMD
             download or Excel parsing on your machine.  ``"imd"`` fetches and
             parses the IMD workbook directly (the pipeline's path; needs the
             ``pipeline`` extra for ``openpyxl``).
    url    : IMD source workbook URL (only used when ``source="imd"``).
    path   : parse this local ``.xlsx`` instead of fetching (overrides ``source``).
    cache_dir : where to store downloaded files and any parsed cache.
    force  : force a fresh download even if the cache looks current.

    Parsed results (``source="imd"``) are cached as parquet keyed by the
    workbook's content hash, so only a genuinely new file triggers a re-parse.
    """
    cache_dir = Path(cache_dir) if cache_dir else _fetch.default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Default path for end users: pull the pre-parsed dataset from the repo.
    if path is None and source == "github":
        return _load_from_github(update=update or force, cache_dir=cache_dir)

    if path is not None:
        wb_path = Path(path)
        sha = _fetch._sha256(wb_path)
        changed = True
    else:
        if update or force or not _parquet_paths(cache_dir)["observations"].exists():
            res = _fetch.fetch_workbook(url=url, cache_dir=cache_dir, force=force)
            wb_path, sha, changed = res.path, res.sha256, res.changed
        else:
            # Offline fast path: reuse whatever we parsed last time.
            wb_path, sha, changed = _fetch._workbook_path(cache_dir), None, False

    pq = _parquet_paths(cache_dir)
    sha_marker = cache_dir / "parsed.sha256"
    cache_valid = (
        not changed
        and all(p.exists() for p in pq.values())
        and (sha is None or (sha_marker.exists() and sha_marker.read_text().strip() == sha))
    )

    if cache_valid:
        frames = {name: _read_parquet(p) for name, p in pq.items()}
    else:
        frames = _parse.parse_workbook(wb_path)
        _write_cache(frames, pq, sha_marker, sha)

    return BestTracks(
        observations=frames["observations"],
        remarks=frames["remarks"],
        storms=frames["storms"],
        sha256=sha,
    )


def _load_from_github(update: bool, cache_dir: Path) -> BestTracks:
    """Load the pre-parsed dataset published in the GitHub repo.

    If ``IMDTRACK_DATA_DIR`` is set, the committed dataset is read straight from
    that local directory instead of the network — handy for offline use, tests,
    and building the docs against the in-repo ``data/``.
    """
    import json

    from . import store

    local = os.environ.get("IMDTRACK_DATA_DIR")
    if local:
        frames = store.read_dataset(Path(local))
        manifest = store.read_manifest(Path(local))
        return BestTracks(
            observations=frames["observations"],
            remarks=frames["remarks"],
            storms=frames["storms"],
            sha256=manifest.source_sha256 if manifest else None,
        )

    paths = _fetch.fetch_data_from_repo(cache_dir=cache_dir, update=update)
    frames = store.read_frame_files(paths)

    sha = None
    try:
        sha = json.loads(Path(paths["manifest"]).read_text()).get("source_sha256")
    except (json.JSONDecodeError, OSError, KeyError):
        pass

    return BestTracks(
        observations=frames["observations"],
        remarks=frames["remarks"],
        storms=frames["storms"],
        sha256=sha,
    )


def update(**kwargs) -> BestTracks:
    """Convenience wrapper for ``load(update=True, ...)``."""
    kwargs.pop("update", None)
    return load(update=True, **kwargs)


def _read_parquet(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if "grade" in df.columns:
        from . import _schema as S

        df["grade"] = pd.Categorical(df["grade"], categories=S.GRADE_ORDER, ordered=True)
    return df


def _write_cache(frames, pq, sha_marker, sha):
    try:
        for name, p in pq.items():
            frames[name].to_parquet(p, index=False)
        if sha:
            sha_marker.write_text(sha)
    except Exception:
        # Parquet needs pyarrow/fastparquet; caching is best-effort only.
        pass
