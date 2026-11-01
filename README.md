# stormtrack

[![CI](https://github.com/syedhamidali/imdtrack/actions/workflows/ci.yml/badge.svg)](https://github.com/syedhamidali/imdtrack/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/syedhamidali/imdtrack/branch/main/graph/badge.svg)](https://codecov.io/gh/syedhamidali/imdtrack)
[![Docs](https://readthedocs.org/projects/imdtrack/badge/?version=latest)](https://imdtrack.readthedocs.io/en/latest/)
[![PyPI](https://img.shields.io/pypi/v/imdtrack.svg)](https://pypi.org/project/imdtrack/)
[![conda-forge](https://img.shields.io/conda/vn/conda-forge/imdtrack.svg)](https://anaconda.org/conda-forge/imdtrack)
[![Python versions](https://img.shields.io/pypi/pyversions/imdtrack.svg)](https://pypi.org/project/imdtrack/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21301659.svg)](https://doi.org/10.5281/zenodo.21301659)

**Tropical-cyclone best tracks and forecasts in Python.** `stormtrack` serves the
[India Meteorological Department (RSMC New Delhi)](https://rsmcnewdelhi.imd.gov.in/)
**best-track record** — every depression and cyclonic storm in the North Indian
Ocean since 1982 — and [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)
in one schema, as tidy **pandas DataFrames** or CF-style **xarray Datasets**, kept up
to date automatically. It adds cross-dataset analysis and comparison, real-time NHC/JTWC
storms and forecasts, and forecast verification.

IMD publishes its record as a single, hand-maintained Excel workbook; `stormtrack`
turns it into clean, analysis-ready tables. The parsed dataset is committed to
this repo (under [`data/`](data/)) and refreshed by a monthly GitHub Action, so
`st.load()` just downloads the pre-parsed data — no Excel parsing on your side.

<p align="center">
  <img src="https://raw.githubusercontent.com/syedhamidali/imdtrack/main/docs/_static/all_tracks_grade.png"
       alt="Every North Indian Ocean cyclone track, 1982–present, coloured by peak IMD grade"
       width="100%">
</p>

<p align="center"><em>Every storm in the record — 428 systems since 1982 — coloured by peak IMD
intensity grade. Two lines of code (below).</em></p>

## Install

**pip** (from [PyPI](https://pypi.org/project/imdtrack/)):

```bash
pip install stormtrack            # core: pandas + pyarrow (reads the published parquet)
pip install stormtrack[xarray]    # + xarray/numpy for .to_xarray()
pip install stormtrack[plot]      # + cartopy/matplotlib for map plotting
pip install stormtrack[all]       # xarray + numpy + openpyxl
```

**conda / mamba / micromamba** (from [conda-forge](https://anaconda.org/conda-forge/imdtrack)) — create a
dedicated environment and install in one step. The commands are interchangeable
across the whole conda family; `conda` ships with Anaconda/Miniconda, while
`mamba`/`micromamba` are faster drop-in replacements:

```bash
# create a new environment named "imd" with stormtrack in it, then activate it
conda create -n imd -c conda-forge stormtrack
conda activate imd

# — or, using mamba / micromamba (same flags) —
mamba create -n imd -c conda-forge stormtrack        # mamba activate imd
micromamba create -n imd -c conda-forge stormtrack   # micromamba activate imd

# add it to an environment you already have active
conda install -c conda-forge stormtrack              # or: mamba / micromamba install ...
```

The conda-forge build **bundles a prebuilt cartopy**, so map plotting works out of
the box — no compiler, no GEOS/PROJ, and no Python-version limit.

**uv** (from [PyPI](https://pypi.org/project/imdtrack/)):

```bash
uv add stormtrack                 # into a uv project  (uv add "stormtrack[plot]" for an extra)
uv pip install stormtrack         # into the active environment
```

| Extra | Adds | For |
|---|---|---|
| *(none)* | pandas, pyarrow | loading the data as DataFrames |
| `xarray` | xarray, numpy | `bt.to_xarray()` |
| `plot` | cartopy, matplotlib | `st.plot_track()` map plots |
| `pipeline` | openpyxl | parsing the IMD workbook yourself (`source="imd"`) |

> With **pip/uv**, `cartopy` has no Python 3.14 wheel yet, so the `[plot]` extra
> needs Python ≤ 3.13 (or a system GEOS+PROJ to build it). Installing from
> **conda-forge** avoids this entirely.

## Usage

```python
import stormtrack as st

bt = st.load()                 # pre-parsed dataset from GitHub (cached)
df = bt.observations            # tidy DataFrame: one row per 3-hourly fix
ds = bt.to_xarray()             # (storm, step) xarray.Dataset

bt = st.load(update=True)      # re-download only if the repo published new data

bt.storm("2020-001")            # one storm's track (AMPHAN)
bt.storms                       # one row per storm (peak grade, max wind, ...)
bt.remarks                      # landfall / weakening notes, linked by storm_id
```

### The tidy `observations` frame

| column | meaning |
|---|---|
| `storm_id` | stable id, `"<year>-<serial>"` e.g. `2020-001` |
| `year`, `serial` | year and serial number of the system within that year |
| `basin` | `BOB` (Bay of Bengal), `ARB` (Arabian Sea), or `LAND` |
| `name` | cyclone name (blank for unnamed / older systems) |
| `time` | observation time (UTC, `datetime64`) |
| `lat`, `lon` | position (°N, °E) |
| `ci_no` | Dvorak CI / T-number |
| `pressure` | estimated central pressure (hPa) |
| `wind` | maximum sustained surface wind (knots) |
| `pressure_drop` | pressure drop / ΔP (hPa) |
| `grade` | ordered category: `D < DD < CS < SCS < VSCS < ESCS < SuCS` |
| `oci`, `oci_diameter` | outermost closed isobar pressure (hPa) & diameter (°) |
| `step` | 0-based fix index within the storm |

### The xarray Dataset

Laid out like [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive):
a ragged track becomes a 2-D `(storm, step)` grid. Per-fix variables span both
dims; storm-level metadata (`name`, `basin`, `year`, …) are `storm` coordinates.

```python
ds = bt.to_xarray()
ds.sel(storm="2020-001")["wind"].max()      # AMPHAN peak intensity
ds.where(ds.basin == "ARB", drop=True)      # Arabian Sea storms only
```

See the [documentation](https://imdtrack.readthedocs.io/) for a full walkthrough
and a North Indian Ocean climatology example.

## Plotting

The optional `[plot]` extra draws publication-quality [Cartopy](https://scitools.org.uk/cartopy/)
maps, coloured by IMD intensity grade. Plot **every track at once** — by peak
grade (the figure above) or by sub-basin:

```python
import stormtrack as st

bt = st.load().clean()                        # QC-clean the whole record
st.plot_tracks(bt.observations, color="grade")   # colour by peak intensity
st.plot_tracks(bt.observations, color="basin")   # Bay of Bengal vs Arabian Sea
```

<p align="center">
  <img src="https://raw.githubusercontent.com/syedhamidali/imdtrack/main/docs/_static/all_tracks_basin.png"
       alt="All tracks coloured by sub-basin: Bay of Bengal vs Arabian Sea" width="100%">
</p>

Or a **single storm**, coloured by grade with genesis / peak / end marked:

```python
st.plot_track(bt.storm("tauktae"), color="grade")   # or any storm_id / name
```

<p align="center">
  <img src="https://raw.githubusercontent.com/syedhamidali/imdtrack/main/docs/_static/track_tauktae.png"
       alt="Cyclone Tauktae (2021) track coloured by IMD grade" width="46%">
</p>

## IBTrACS and cross-dataset analysis

The same package loads the North Indian Ocean slice of
[IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive) in
the **identical schema**, so every analysis runs on either record. Like the IMD data
it is committed to the repo ([`data/ibtracs/`](data/ibtracs/), ~1 MB) and refreshed by
the monthly Action, so there is no CSV parsing on your side.

```python
import stormtrack as st

imd_bt = st.load()                      # IMD RSMC New Delhi, 1982-
ib_bt = st.load_ibtracs()               # IBTrACS North Indian Ocean, 1842-
ib_wp = st.load_ibtracs(basin="WP", source="ncei")   # any other basin, straight from NOAA

A = st.analysis                         # works on either dataset
A.lifetime_max(ib_bt)                    # peak intensity, time and place per storm
A.rapid_intensification(imd_bt)          # >= 30 kt / 24 h events
A.annual_counts(ib_bt)                   # storms per year by strength
A.ace(ib_bt)                             # accumulated cyclone energy
A.match_controls(events, pool)           # matched control storms for composites

cmp = st.compare_tracks(imd_bt, ib_bt)  # pair storms by track, compare every common fix
cmp.summary()                            # position / wind / pressure agreement
```

`compare_tracks(..., ib_wind="usa")` compares IMD with JTWC's independent estimate
(1-min wind, so not like-for-like with IMD's 3-min; the WMO guidance only converts 1-min ↔ 10-min, see `analysis.convert_vmax`), while `ib_wind="wmo"`
checks that IBTrACS reproduces IMD's own submission. From the shell:
`stormtrack compare --out diffs.csv`.

## Real-time storms, forecast verification and cones

NHC and JTWC publish ATCF decks; `stormtrack.realtime` reads them into the same schema,
and `stormtrack.verification` scores any forecast against any best track — e.g. an NHC or
JTWC forecast against the IMD record. (IMD, JMA, BoM and Météo-France offer no
machine-readable forecast feed, so their forecasts are not supported.)

```python
io = st.realtime.active_storms("jtwc", basins=["io"])   # live JTWC North Indian Ocean
gd = st.realtime.get_guidance("AL042026")                # NHC a-deck: every model & cycle
err = st.verification.forecast_errors(gd, best_track)    # track / wind errors by lead time
radii = st.verification.error_radii(err, pct=67)         # NHC's 67 % cone-circle definition
st.plot_forecast(fc, best=track, radii_km=radii)         # forecast + cone map
```

Methods and definitions are referenced to the literature in
[`docs/references.md`](docs/references.md).

## Staying up to date

A [monthly GitHub Action](.github/workflows/update-dataset.yml) re-fetches the
IMD workbook (and IBTrACS) and, only if it parses and passes validation, updates `data/` — a
broken upload can never overwrite the good published data. You normally don't
have to do anything; `st.load(update=True)` pulls the latest.

## Data quality

The library mirrors the IMD workbook faithfully, including its occasional
data-entry errors. Two conservative, **non-destructive** checks flag them — the
source values are never altered:

- **`pos_suspect`** — a fix whose coordinates imply an impossible jump (isolated
  position spike), e.g. a corrupted latitude.
- **`date_suspect`** — a day/month-transposed date, e.g. Nargis (2008) where
  May 1–3 were stored as "01/05, 02/05, 03/05" (Jan/Feb/Mar 5).

```python
bt = st.load()
bt.observations.query("pos_suspect or date_suspect")   # inspect flagged fixes
bt.clean()                        # drop position spikes (or clean(how="mask"))
bt.clean(fix_dates=True)          # also swap day/month back and re-order the track
```

These catch the common, well-defined cases; a few storms have messier date
corruption that is left as-is (visible as an implausibly long `start_time`–`end_time` span).

## Notes & caveats

- Data © India Meteorological Department. This library only reformats it; verify
  against IMD for operational use. The most recent season is *tentative* until
  IMD's post-season review.
- Older years often lack storm names and some fields (e.g. central pressure);
  those appear as `NaN`.

## Citation

Please cite `stormtrack` via its Zenodo **Concept DOI** — stable across releases,
always resolving to the latest version:

> Syed, H. A. (2026). *stormtrack: A Python library for the IMD North Indian Ocean
> cyclone best-track record.* https://doi.org/10.5281/zenodo.21301659

GitHub's "Cite this repository" button reads [`CITATION.cff`](CITATION.cff).

## License

BSD 3-Clause. See [LICENSE](LICENSE).
