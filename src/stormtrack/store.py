"""Read / write the canonical on-disk dataset (parquet frames + a manifest).

This is the format that gets committed into the repo under ``data/`` and that
end users download.  Three parquet files hold the frames; ``manifest.json``
records provenance (which IMD workbook they came from) and a few summary counts
so freshness and integrity can be checked cheaply without opening the parquet.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from . import _schema as S

FRAME_NAMES = ("observations", "remarks", "storms")
MANIFEST_NAME = "manifest.json"
FORMAT_VERSION = 1


@dataclass
class Manifest:
    format: int
    source_url: str
    source_sha256: str
    generated_at: str
    n_storms: int
    n_obs: int
    n_remarks: int
    year_min: Optional[int]
    year_max: Optional[int]

    @classmethod
    def from_frames(cls, frames: dict, source_url: str, source_sha256: str) -> Manifest:
        obs = frames["observations"]
        years = (
            obs["year"] if ("year" in obs.columns and not obs.empty) else pd.Series(dtype="int64")
        )
        return cls(
            format=FORMAT_VERSION,
            source_url=source_url,
            source_sha256=source_sha256,
            generated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            n_storms=int(len(frames["storms"])),
            n_obs=int(len(obs)),
            n_remarks=int(len(frames["remarks"])),
            year_min=int(years.min()) if len(years) else None,
            year_max=int(years.max()) if len(years) else None,
        )


def _frame_path(data_dir: Path, name: str) -> Path:
    return data_dir / f"{name}.parquet"


def manifest_path(data_dir: Path) -> Path:
    return data_dir / MANIFEST_NAME


def read_manifest(data_dir: Path) -> Optional[Manifest]:
    p = manifest_path(Path(data_dir))
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
        # Ignore unknown keys so the format can grow without breaking readers.
        fields = {f: raw.get(f) for f in Manifest.__dataclass_fields__}
        return Manifest(**fields)
    except (json.JSONDecodeError, OSError, TypeError):
        return None


def dataset_exists(data_dir: Path) -> bool:
    data_dir = Path(data_dir)
    return manifest_path(data_dir).exists() and all(
        _frame_path(data_dir, n).exists() for n in FRAME_NAMES
    )


def write_dataset(frames: dict, data_dir: Path, source_url: str, source_sha256: str) -> Manifest:
    """Atomically write the three frames + manifest into ``data_dir``.

    Each file is written to a ``.tmp`` sibling and then ``os.replace``-d into
    place, so a crash mid-write can never leave a half-written committed dataset.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    for name in FRAME_NAMES:
        dst = _frame_path(data_dir, name)
        tmp = dst.with_suffix(".parquet.tmp")
        frames[name].to_parquet(tmp, index=False)
        os.replace(tmp, dst)

    manifest = Manifest.from_frames(frames, source_url, source_sha256)
    mp = manifest_path(data_dir)
    tmp = mp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(manifest), indent=2) + "\n")
    os.replace(tmp, mp)
    return manifest


def read_dataset(data_dir: Path) -> dict:
    """Read the three parquet frames from ``data_dir`` into DataFrames."""
    data_dir = Path(data_dir)
    frames = {name: pd.read_parquet(_frame_path(data_dir, name)) for name in FRAME_NAMES}
    _restore_categoricals(frames)
    return frames


def read_frame_files(paths: dict) -> dict:
    """Read frames from an explicit ``{name: path}`` mapping (used by the loader)."""
    frames = {name: pd.read_parquet(paths[name]) for name in FRAME_NAMES}
    _restore_categoricals(frames)
    return frames


def _restore_categoricals(frames: dict) -> None:
    obs = frames.get("observations")
    if obs is not None and "grade" in obs.columns:
        obs["grade"] = pd.Categorical(obs["grade"], categories=S.GRADE_ORDER, ordered=True)
