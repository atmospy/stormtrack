"""Real-time best tracks and forecasts from ATCF servers (NHC, JTWC mirrors).

Only agencies that publish machine-readable ATCF are supported. As of this
writing neither IMD nor JMA, BoM or Météo-France offers a track-forecast feed in
that (or any other documented) format — IMD's cyclone bulletins are text/PDF — so
their forecasts cannot be read programmatically; their *best tracks* are the
archived products already handled by :func:`stormtrack.load` and
:func:`stormtrack.load_ibtracs`.

>>> import stormtrack as st
>>> now = st.realtime.active_storms("nhc")             # Atlantic / East + Central Pacific
>>> io = st.realtime.active_storms("jtwc", basins=["io"])   # JTWC North Indian Ocean
>>> fc = st.realtime.get_forecast("AL042026")          # NHC official forecast (OFCL)
>>> gd = st.realtime.get_guidance("AL042026")          # every model, every cycle

JTWC data come from the open UCAR RAL mirror of the b-decks by default. The files
JTWC's own forecasts are distributed in (``.fst``/``.sum``) are served from mirrors
that may block automated access; pass ``url=`` to :func:`get_forecast` for a mirror
you can reach.
"""

from __future__ import annotations

import gzip
import re
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from .atcf import best_track_frame, parse_atcf
from .core import BestTracks
from .ibtracs import summarize_storms

NHC_ATCF = "https://ftp.nhc.noaa.gov/atcf"
UCAR_BDECKS = "https://hurricanes.ral.ucar.edu/repository/data/bdecks_open/{year}/"
JTWC_FST_MIRRORS = (
    "https://www.ssd.noaa.gov/PS/TROP/DATA/ATCF/JTWC/{id}.fst",
    "https://www.nrlmry.navy.mil/atcf_web/docs/current_storms/{id}.fst",
)
_UA = {"User-Agent": "stormtrack (https://github.com/atmospy/stormtrack)"}


def _get(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        data = r.read()
    return gzip.decompress(data) if url.endswith(".gz") else data


def _list(url: str, pattern: str, timeout: float = 60.0) -> list:
    html = _get(url, timeout).decode("utf-8", "replace")
    return sorted(set(re.findall(pattern, html)))


def _now(now) -> pd.Timestamp:
    return (
        pd.Timestamp(now)
        if now is not None
        else pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
    )


def active_storms(
    source: str = "nhc",
    basins: Optional[list] = None,
    max_age_hours: float = 12.0,
    invests: bool = False,
    now=None,
    timeout: float = 60.0,
) -> BestTracks:
    """Best tracks of currently active systems, as a :class:`~stormtrack.BestTracks`.

    Parameters
    ----------
    source : ``"nhc"`` (b-decks for AL/EP/CP on the NHC server) or ``"jtwc"``
             (JTWC b-decks for any basin, via the open UCAR RAL mirror).
    basins : ATCF basin codes to keep, e.g. ``["io"]``. Default: all (``nhc``);
             ``io``, ``sh`` and ``wp`` (``jtwc``).
    max_age_hours : drop systems whose latest fix is older than this — the
             server keeps finished storms' files for the whole season.
    invests : keep invest areas (ATCF numbers 90–99). Default: only numbered storms.
    now : reference time (UTC) for the age cut, for reproducibility. Default: now.

    The returned ``source`` is ``"atcf-nhc"`` / ``"atcf-jtwc"``; ``basin`` uses IBTrACS
    codes (``IO`` -> ``NI``). Winds are 1-minute (knots) for both agencies.
    """
    if source not in ("nhc", "jtwc"):
        raise ValueError("source must be 'nhc' or 'jtwc'")
    t_now = _now(now)
    if source == "nhc":
        base = f"{NHC_ATCF}/btk/"
        allowed = [b.lower() for b in (basins or ["al", "ep", "cp"])]
        year = t_now.year
    else:
        year = t_now.year
        base = UCAR_BDECKS.format(year=year)
        allowed = [b.lower() for b in (basins or ["io", "sh", "wp"])]
    names = _list(base, r"(b[a-z]{2}\d{6}\.dat)", timeout)
    frames = []
    for fn in names:
        code, cy, yr = fn[1:3], int(fn[3:5]), int(fn[5:9])
        if code not in allowed or yr != year or (cy >= 90 and not invests):
            continue
        obs = best_track_frame(parse_atcf(_get(base + fn, timeout)))
        if obs.empty or (t_now - obs["time"].max()) > pd.Timedelta(hours=max_age_hours):
            continue
        frames.append(obs)
    obs = pd.concat(frames, ignore_index=True) if frames else best_track_frame(parse_atcf(""))
    return BestTracks(
        observations=obs,
        remarks=pd.DataFrame(columns=["storm_id", "remark"]),
        storms=summarize_storms(obs),
        sha256=None,
        source=f"atcf-{source}",
    )


def get_forecast(
    storm_id: str,
    source: str = "nhc",
    tech: Optional[str] = None,
    url: Optional[str] = None,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """The agency's current official forecast for one storm (an ATCF f-deck).

    ``storm_id`` is the ATCF id, e.g. ``"AL042026"`` or ``"IO042026"``. ``tech``
    defaults to ``"OFCL"`` (NHC) or ``"JTWC"``. For ``source="jtwc"`` the known
    mirrors are tried in turn unless ``url`` (a ``.fst`` URL) is given. Returns the
    :func:`~stormtrack.atcf.parse_atcf` frame filtered to ``tech``, one row per lead
    time ``tau`` (hours), with wind radii.
    """
    sid = storm_id.lower()
    if source == "nhc":
        urls = [url or f"{NHC_ATCF}/fst/{sid}.fst"]
        tech = tech or "OFCL"
    elif source == "jtwc":
        urls = [url] if url else [m.format(id=sid) for m in JTWC_FST_MIRRORS]
        tech = tech or "JTWC"
    else:
        raise ValueError("source must be 'nhc' or 'jtwc'")
    errors = []
    for u in urls:
        try:
            deck = parse_atcf(_get(u, timeout))
        except OSError as exc:  # HTTPError/URLError are OSErrors
            errors.append(f"{u}: {exc}")
            continue
        fc = deck[deck["tech"] == tech.upper()]
        if len(fc):
            return fc.reset_index(drop=True)
        errors.append(f"{u}: no {tech.upper()} rows")
    raise LookupError(f"no {source} forecast for {storm_id}: " + "; ".join(errors))


def get_guidance(
    storm_id: str,
    techs: Optional[list] = None,
    source: str = "nhc",
    url: Optional[str] = None,
    timeout: float = 120.0,
) -> pd.DataFrame:
    """Every forecast cycle of every model/technique for one storm (an ATCF a-deck).

    NHC's public a-decks hold the official forecast (``OFCL``), global and regional
    models (``AVNO``, ``HWRF`` ...), consensus aids and ensembles. Use
    :func:`stormtrack.verification.forecast_errors` to score them against a best track.
    ``techs`` restricts the result; ``url`` overrides the a-deck location.
    """
    if source != "nhc" and not url:
        raise ValueError("only NHC a-decks have a built-in location; pass url= for others")
    sid = storm_id.lower()
    deck = parse_atcf(_get(url or f"{NHC_ATCF}/aid_public/a{sid}.dat.gz", timeout))
    if techs:
        deck = deck[deck["tech"].isin([t.upper() for t in techs])]
    return deck.reset_index(drop=True)


def interpolate_forecast(fc: pd.DataFrame, step: int = 6) -> pd.DataFrame:
    """Linearly interpolate a forecast to a regular ``step``-hour grid.

    Positions (longitude unwrapped across the dateline), ``vmax`` and ``mslp`` are
    interpolated in time; ``ty`` is carried forward from the latest forecast point.
    Useful to compute forecast ACE (:func:`stormtrack.analysis.ace` on the result) or to
    compare with 6-hourly best tracks. The 6-hourly choice follows tropycal.
    """
    fc = fc.sort_values("tau").drop_duplicates("tau")
    tau = np.arange(int(fc["tau"].min()), int(fc["tau"].max()) + 1, step)
    lon = np.degrees(np.unwrap(np.radians(fc["lon"].to_numpy())))
    out = pd.DataFrame({"tau": tau})
    out["atcf_id"] = fc["atcf_id"].iloc[0]
    out["tech"] = fc["tech"].iloc[0]
    out["init"] = fc["init"].iloc[0]
    out["time"] = out["init"] + pd.to_timedelta(out["tau"], unit="h")
    out["lat"] = np.interp(tau, fc["tau"], fc["lat"])
    out["lon"] = (np.interp(tau, fc["tau"], lon) + 180) % 360 - 180
    for c in ("vmax", "mslp"):
        ok = fc[c].notna()
        out[c] = np.interp(tau, fc.loc[ok, "tau"], fc.loc[ok, c]) if ok.sum() else np.nan
    idx = np.searchsorted(fc["tau"].to_numpy(), tau, side="right") - 1
    out["ty"] = fc["ty"].to_numpy()[np.clip(idx, 0, None)]
    return out
