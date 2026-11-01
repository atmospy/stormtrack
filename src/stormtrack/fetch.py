"""Download and cache the IMD Best Track workbook.

The IMD publishes a *single* workbook containing every year, and replaces it in
place whenever the record is updated (new storms, revised best tracks).  So
"keeping up to date" just means re-fetching that file when the server's copy
changes.  We use a conditional GET (ETag / Last-Modified) so repeated calls are
cheap and only download when something actually changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import _repo
from .store import FRAME_NAMES, MANIFEST_NAME

DEFAULT_URL = (
    "https://rsmcnewdelhi.imd.gov.in/download.php"
    "?path=uploads/best-track/78b4b0_Best_Tracks__Data__1982-2026_.xlsx"
)


def default_cache_dir() -> Path:
    root = _repo.env("CACHE")
    if root:
        return Path(root)
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "stormtrack"


@dataclass
class FetchResult:
    path: Path  # local workbook file
    changed: bool  # True if this call downloaded new bytes
    sha256: str  # content hash of the workbook
    from_cache: bool  # True if the cached copy was reused


def _meta_path(cache_dir: Path) -> Path:
    return cache_dir / "workbook.meta.json"


def _workbook_path(cache_dir: Path) -> Path:
    return cache_dir / "best_tracks.xlsx"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_workbook(
    url: str = DEFAULT_URL,
    cache_dir: Optional[Path] = None,
    force: bool = False,
    timeout: float = 120.0,
) -> FetchResult:
    """Ensure a current copy of the workbook is on disk, downloading if needed.

    Uses stored ETag / Last-Modified for a conditional request; a ``304 Not
    Modified`` response (or ``force=False`` with no prior download) reuses the
    cached file.  Only the standard library is used, so there is no hard
    dependency on ``requests``.
    """
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    wb_path = _workbook_path(cache_dir)
    meta_path = _meta_path(cache_dir)

    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            meta = {}

    have_cache = wb_path.exists()
    if have_cache and not force:
        # Cheap conditional request: reuse cache unless the server file changed.
        req = urllib.request.Request(url)
        if meta.get("etag"):
            req.add_header("If-None-Match", meta["etag"])
        if meta.get("last_modified"):
            req.add_header("If-Modified-Since", meta["last_modified"])
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                new_meta = _headers_to_meta(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return FetchResult(
                    wb_path,
                    changed=False,
                    sha256=meta.get("sha256", _sha256(wb_path)),
                    from_cache=True,
                )
            raise
    else:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
            new_meta = _headers_to_meta(resp)

    new_sha = hashlib.sha256(data).hexdigest()
    if have_cache and new_sha == meta.get("sha256"):
        # Server returned 200 but bytes are identical to what we already have.
        _write_meta(meta_path, {**meta, **new_meta, "sha256": new_sha})
        return FetchResult(wb_path, changed=False, sha256=new_sha, from_cache=True)

    tmp = wb_path.with_suffix(".xlsx.tmp")
    tmp.write_bytes(data)
    tmp.replace(wb_path)
    _write_meta(meta_path, {**new_meta, "sha256": new_sha, "url": url})
    return FetchResult(wb_path, changed=True, sha256=new_sha, from_cache=False)


def _headers_to_meta(resp) -> dict:
    return {
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
    }


def _write_meta(meta_path: Path, meta: dict) -> None:
    meta_path.write_text(json.dumps({k: v for k, v in meta.items() if v is not None}, indent=2))


# --------------------------------------------------------------------------- #
# Published dataset: download the committed parquet from the GitHub repo.
# --------------------------------------------------------------------------- #


def _repo_data_dir(cache_dir: Path) -> Path:
    return cache_dir / "repo_data"


def _download_if_changed(
    url: str, dst: Path, meta_path: Path, update: bool, timeout: float
) -> bool:
    """Fetch ``url`` to ``dst`` using a conditional GET. Returns True if updated.

    When ``update`` is False and a cached copy already exists, the network is not
    touched at all — the cached file is reused as-is.
    """
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            meta = {}

    if dst.exists() and not update:
        return False

    req = urllib.request.Request(url)
    if dst.exists():
        if meta.get("etag"):
            req.add_header("If-None-Match", meta["etag"])
        if meta.get("last_modified"):
            req.add_header("If-Modified-Since", meta["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            new_meta = _headers_to_meta(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and dst.exists():
            return False
        raise

    tmp = dst.with_suffix(dst.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dst)
    _write_meta(meta_path, {**meta, **new_meta, "url": url})
    return True


def fetch_data_from_repo(
    cache_dir: Optional[Path] = None,
    update: bool = False,
    timeout: float = 120.0,
) -> dict:
    """Download the published parquet dataset from the GitHub repo into the cache.

    Returns ``{"observations": path, "remarks": path, "storms": path,
    "manifest": path}``.  With ``update=False`` a previously-cached copy is
    reused offline; ``update=True`` does a cheap conditional GET per file.
    """
    cache_dir = Path(cache_dir) if cache_dir else default_cache_dir()
    data_dir = _repo_data_dir(cache_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    paths: dict = {}
    for name in (*FRAME_NAMES, "manifest"):
        filename = MANIFEST_NAME if name == "manifest" else f"{name}.parquet"
        dst = data_dir / filename
        meta_path = data_dir / f"{filename}.meta.json"
        _download_if_changed(
            _repo.raw_url(filename), dst, meta_path, update=update, timeout=timeout
        )
        paths[name] = dst
    return paths
