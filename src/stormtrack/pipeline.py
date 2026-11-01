"""Rebuild the committed dataset from the IMD workbook.

This is what the scheduled GitHub Action runs.  It is deliberately *fail-safe*:

1. Download the current IMD workbook.
2. If its content hash matches the published manifest, there is nothing to do.
3. Otherwise parse it, then run the validators.  Only if every check passes are
   the committed parquet files replaced (atomically).
4. If parsing or any validation fails, the exception propagates: the committed
   dataset is left **untouched** and the process exits non-zero, so the workflow
   goes red and notifies you.  A broken IMD upload can never overwrite good data.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import _repo, store, validate
from . import fetch as _fetch
from . import parse as _parse
from .fetch import DEFAULT_URL


@dataclass
class BuildResult:
    changed: bool
    reason: str
    source_sha256: str
    manifest: Optional[store.Manifest] = None


def build(
    data_dir: Path,
    url: str = DEFAULT_URL,
    force: bool = False,
    cache_dir: Optional[Path] = None,
) -> BuildResult:
    """Fetch → (maybe) parse → validate → publish into ``data_dir``.

    Returns a :class:`BuildResult`.  Raises :class:`validate.ValidationError`
    (or a parse error) *without* modifying ``data_dir`` if the new data is bad.
    """
    data_dir = Path(data_dir)
    previous = store.read_manifest(data_dir)

    # Always pull fresh bytes; we decide "changed" by comparing content hashes
    # against the published manifest rather than trusting a local HTTP cache.
    res = _fetch.fetch_workbook(url=url, cache_dir=cache_dir, force=True)
    sha = res.sha256

    up_to_date = (
        not force
        and previous is not None
        and previous.source_sha256 == sha
        and store.dataset_exists(data_dir)
    )
    if up_to_date:
        return BuildResult(changed=False, reason="source unchanged", source_sha256=sha)

    # A new (or forced) workbook: parse and validate before touching data_dir.
    frames = _parse.parse_workbook(res.path)
    validate.validate_frames(frames)
    # Completeness: every positional row in the workbook must have been parsed.
    validate.validate_completeness(frames, _parse.count_positional_rows(res.path))
    validate.validate_against_previous(frames, previous)

    manifest = store.write_dataset(frames, data_dir, source_url=url, source_sha256=sha)
    reason = "initial build" if previous is None else "source changed"
    return BuildResult(changed=True, reason=reason, source_sha256=sha, manifest=manifest)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="stormtrack-build",
        description="Rebuild the committed dataset from the IMD workbook (CI pipeline).",
    )
    p.add_argument(
        "--data-dir",
        default=_repo.DATA_DIR_NAME,
        help=f"Directory to write the dataset into (default: ./{_repo.DATA_DIR_NAME}).",
    )
    p.add_argument("--url", default=DEFAULT_URL, help="Source workbook URL.")
    p.add_argument("--force", action="store_true", help="Rebuild even if the source is unchanged.")
    p.add_argument(
        "--cache-dir",
        default=None,
        help="Where to store the downloaded workbook (default: OS cache dir).",
    )
    args = p.parse_args(argv)

    try:
        result = build(
            Path(args.data_dir),
            url=args.url,
            force=args.force,
            cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        )
    except validate.ValidationError as exc:
        print(f"::error::dataset validation failed: {exc}", file=sys.stderr)
        print("Published dataset left unchanged.", file=sys.stderr)
        return 2
    except Exception as exc:  # parse/download failure — also fail loudly.
        print(f"::error::pipeline failed: {exc}", file=sys.stderr)
        print("Published dataset left unchanged.", file=sys.stderr)
        return 1

    if result.changed:
        m = result.manifest
        print(
            f"UPDATED ({result.reason}): {m.n_storms} storms, {m.n_obs} fixes, "
            f"{m.year_min}-{m.year_max}, source sha256={result.source_sha256[:12]}"
        )
    else:
        print(f"NO CHANGE ({result.reason}); source sha256={result.source_sha256[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
