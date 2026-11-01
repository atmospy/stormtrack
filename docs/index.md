# stormtrack

**Tropical-cyclone best tracks and forecasts — the IMD RSMC New Delhi record and
IBTrACS as tidy pandas DataFrames and CF-style xarray Datasets, plus real-time
NHC/JTWC data and forecast verification — kept up to date automatically.**

The parsed dataset lives in the project's GitHub repo (rebuilt from the IMD
workbook by a monthly, validated pipeline). `st.load()` downloads that
pre-parsed data — no Excel scraping on your machine.

```python
import stormtrack as st

bt = st.load()                       # pre-parsed dataset from GitHub (cached)
bt.observations                       # one tidy row per 3-hourly fix
bt.storms                             # one summary row per storm
bt.to_xarray()                        # (storm, step) xarray.Dataset
st.plot_track(bt.storm("tauktae"))   # cartopy map  (needs the [plot] extra)
```

New here? Head to {doc}`installation`, then the {doc}`examples/quickstart`. The
{doc}`userguide` covers loading, the data model, updates, and data quality, and
the {doc}`api` documents every function.

## Citation

If you use `stormtrack` in your work, please cite it via its Zenodo **Concept
DOI** — this DOI represents all versions and always resolves to the latest, so
it stays stable across releases:

> Syed, H. A. (2026). *stormtrack: A Python library for the IMD North Indian Ocean
> cyclone best-track record.* <https://doi.org/10.5281/zenodo.21301659>

The repository's [`CITATION.cff`](https://github.com/atmospy/stormtrack/blob/main/CITATION.cff)
carries the machine-readable metadata (GitHub's "Cite this repository" button
reads it).

```{toctree}
:hidden:

installation
userguide
api
contributing
```
