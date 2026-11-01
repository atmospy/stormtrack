# Loading the data

The parsed dataset lives in the project's GitHub repo (rebuilt from the IMD
workbook by a monthly, validated pipeline). {func}`stormtrack.load` downloads that
pre-parsed data — no Excel scraping on your machine.

```python
import stormtrack as st

bt = st.load()                 # pre-parsed dataset from GitHub (cached locally)
bt.observations                 # tidy DataFrame: one row per 3-hourly fix
bt.storms                       # one summary row per storm
bt.remarks                      # free-text landfall / weakening notes
bt.to_xarray()                  # (storm, step) xarray.Dataset

bt = st.load(update=True)      # re-download only if the repo published new data
```

## Selecting a storm

{meth}`~stormtrack.BestTracks.storm` accepts a `storm_id` **or a name**
(case-insensitive):

```python
bt.storm("2020-001")            # by id
bt.storm("amphan")              # by name
```

## Where the data comes from

By default `st.load()` pulls the pre-parsed parquet from GitHub. Two other
sources are available:

```python
st.load(source="imd")          # fetch + parse the IMD workbook yourself
                                # (needs the [pipeline] extra: openpyxl)
st.load(path="best_tracks.xlsx")   # parse a local workbook
```

## Cache & configuration

Downloads are cached under `~/.cache/stormtrack` (override with `STORMTRACK_CACHE`).
Point the loader at a local committed dataset with `STORMTRACK_DATA_DIR` (used by
the docs build and offline work), or a fork's data repo with `STORMTRACK_REPO`.
