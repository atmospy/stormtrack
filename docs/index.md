# imdtrack

**IMD RSMC New Delhi cyclone best-track data as tidy pandas DataFrames and
CF-style xarray Datasets — kept up to date automatically.**

The parsed dataset lives in the project's GitHub repo (rebuilt from the IMD
workbook by a monthly, validated pipeline). `imd.load()` downloads that
pre-parsed data — no Excel scraping on your machine.

```python
import imdtrack as imd

bt = imd.load()                       # pre-parsed dataset from GitHub (cached)
bt.observations                       # one tidy row per 3-hourly fix
bt.storms                             # one summary row per storm
bt.to_xarray()                        # (storm, step) xarray.Dataset
imd.plot_track(bt.storm("tauktae"))   # cartopy map  (needs the [plot] extra)
```

New here? Head to {doc}`installation`, then the {doc}`examples/quickstart`. The
{doc}`userguide` covers loading, the data model, updates, and data quality, and
the {doc}`api` documents every function.

## Citation

If you use `imdtrack` in your work, please cite it via its Zenodo **Concept
DOI** — this DOI represents all versions and always resolves to the latest, so
it stays stable across releases:

> Syed, H. A. (2026). *imdtrack: A Python library for the IMD North Indian Ocean
> cyclone best-track record.* <https://doi.org/10.5281/zenodo.21301659>

The repository's [`CITATION.cff`](https://github.com/syedhamidali/imdtrack/blob/main/CITATION.cff)
carries the machine-readable metadata (GitHub's "Cite this repository" button
reads it).

```{toctree}
:hidden:

installation
userguide
api
contributing
```
