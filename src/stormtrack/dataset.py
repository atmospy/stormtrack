"""Build an xarray Dataset from the tidy observations frame.

Best-track data is *ragged*: every storm has a different number of fixes.  We
follow the IBTrACS convention and lay the data out on a 2-D ``(storm, step)``
grid, padding the tail of shorter storms with NaN / NaT.  Storm-level metadata
(name, basin, year ...) live on the ``storm`` dimension; per-fix variables
(lat, lon, wind ...) span ``(storm, step)``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import _schema as S

_ATTRS = {
    "imd": {
        "title": "IMD RSMC New Delhi best track data",
        "source": "India Meteorological Department (rsmcnewdelhi.imd.gov.in)",
    },
    "ibtracs": {
        "title": "IBTrACS best track data",
        "source": "NOAA NCEI International Best Track Archive for Climate Stewardship",
    },
}

_OBS_VARS = [
    "time",
    "lat",
    "lon",
    "ci_no",
    "pressure",
    "wind",
    "pressure_drop",
    "grade",
    "oci",
    "oci_diameter",
]
# IBTrACS-only per-fix variables (present when the frame comes from load_ibtracs)
_EXTRA_VARS = ["wmo_wind", "usa_wind", "wmo_pres", "usa_pres", "sshs", "dist2land", "storm_speed"]


def to_xarray(observations: pd.DataFrame, storms: pd.DataFrame | None = None, source: str = "imd"):
    """Convert the tidy observations frame to an ``xarray.Dataset``.

    Requires :mod:`xarray` (and ``numpy``).  Import is deferred so that pandas
    users don't pay for it.
    """
    import xarray as xr

    if observations.empty:
        return xr.Dataset()

    obs = observations
    storm_ids = list(dict.fromkeys(obs["storm_id"]))  # preserve chronological order
    n_storm = len(storm_ids)
    max_step = int(obs["step"].max()) + 1
    sidx = {sid: i for i, sid in enumerate(storm_ids)}

    rows = obs["storm_id"].map(sidx).to_numpy()
    cols = obs["step"].to_numpy()

    data_vars = {}
    for var in [v for v in _OBS_VARS + _EXTRA_VARS if v in obs.columns]:
        col = obs[var]
        if var == "time":
            grid = np.full((n_storm, max_step), np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
            grid[rows, cols] = col.to_numpy(dtype="datetime64[ns]")
        elif var == "grade":
            grid = np.full((n_storm, max_step), "", dtype=object)
            grid[rows, cols] = col.astype(object).where(col.notna(), "").to_numpy()
        else:
            grid = np.full((n_storm, max_step), np.nan, dtype="float64")
            grid[rows, cols] = col.to_numpy(dtype="float64")
        attrs = S.FIELD_ATTRS.get(var, {})
        data_vars[var] = (("storm", "step"), grid, attrs)

    if storms is None:
        from .parse import _summarize_storms

        storms = _summarize_storms(obs)
    storms = storms.set_index("storm_id").reindex(storm_ids)

    coords = {
        "storm": ("storm", np.array(storm_ids, dtype=object)),
        "step": ("step", np.arange(max_step)),
        "name": (
            "storm",
            storms["name"].astype(object).where(storms["name"].notna(), "").to_numpy(),
        ),
        "basin": (
            "storm",
            storms["basin"].astype(object).where(storms["basin"].notna(), "").to_numpy(),
        ),
        "year": ("storm", storms["year"].to_numpy(dtype="int64")),
        "serial": ("storm", storms["serial"].to_numpy(dtype="int64")),
        "peak_grade": (
            "storm",
            storms["peak_grade"].astype(object).where(storms["peak_grade"].notna(), "").to_numpy(),
        ),
    }

    ds = xr.Dataset(data_vars=data_vars, coords=coords)
    ds.attrs.update(
        {
            **_ATTRS[source],
            "featureType": "trajectory",
            "n_storms": n_storm,
            "grade_definitions": "; ".join(f"{k}={v}" for k, v in S.GRADE_LONG.items()),
        }
    )
    return ds
