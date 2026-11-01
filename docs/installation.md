# Installation

stormtrack is published on both [PyPI](https://pypi.org/project/stormtrack/) (for
`pip` / `uv`) and [conda-forge](https://anaconda.org/conda-forge/stormtrack) (for
the whole conda family). Pick whichever matches your stack — the core package is
identical either way.

## pip

```bash
pip install stormtrack            # core: pandas + pyarrow (reads the published parquet)
pip install stormtrack[xarray]    # + xarray/numpy for .to_xarray()
pip install stormtrack[plot]      # + cartopy/matplotlib for map plotting
pip install stormtrack[all]       # xarray + numpy + openpyxl
```

It's good practice to install into a virtual environment rather than the system
Python:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install stormtrack
```

## conda / mamba / micromamba

stormtrack is on **conda-forge**, so it installs with any tool in the conda family.
`conda` ships with [Anaconda](https://www.anaconda.com/download) or the smaller
[Miniconda](https://docs.anaconda.com/miniconda/); [`mamba`](https://mamba.readthedocs.io/)
and [`micromamba`](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html)
are faster, drop-in replacements that take the **same commands and flags** — just
swap the executable name.

The recommended pattern is a dedicated environment. Create one with stormtrack
already in it, then activate it:

```bash
# conda (Anaconda / Miniconda)
conda create -n imd -c conda-forge stormtrack
conda activate imd

# mamba
mamba create -n imd -c conda-forge stormtrack
mamba activate imd

# micromamba (no base conda install required)
micromamba create -n imd -c conda-forge stormtrack
micromamba activate imd
```

Pin a Python version at creation time if you need one, and add any extras' deps
as ordinary conda packages (they live on conda-forge too):

```bash
conda create -n imd -c conda-forge python=3.12 stormtrack xarray cartopy matplotlib
```

To add stormtrack to an environment you already have active, use `install` instead
of `create` (again, `conda` / `mamba` / `micromamba` are interchangeable):

```bash
conda install -c conda-forge stormtrack
```

```{tip}
The conda-forge build **bundles a prebuilt cartopy**, so map plotting works with
no compiler and no system GEOS/PROJ — the easiest route if you want the plotting
features.
```

## uv

[uv](https://docs.astral.sh/uv/) installs the same PyPI package, very fast:

```bash
uv add stormtrack                 # add to a uv-managed project's dependencies
uv add "stormtrack[plot]"         # …with an extra
uv pip install stormtrack         # into the active/target environment (pip-compatible)
```

You can also run a throwaway session with stormtrack available, without installing
it into a project:

```bash
uv run --with stormtrack python -c "import stormtrack as st; print(st.load())"
```

## Optional extras

| Extra | Adds | For |
|---|---|---|
| *(none)* | pandas, pyarrow | loading the data as DataFrames |
| `xarray` | xarray, numpy | {meth}`~stormtrack.BestTracks.to_xarray` |
| `plot` | cartopy, matplotlib | {func}`~stormtrack.plot_track` / {func}`~stormtrack.plot_tracks` maps |
| `pipeline` | openpyxl | parsing the IMD workbook yourself (`source="imd"`) |

```{note}
Extras apply to the **pip / uv** install. With those, `cartopy` has no Python 3.14
wheel yet, so `[plot]` needs Python ≤ 3.13 (or a system GEOS + PROJ to build it).
The **conda-forge** package sidesteps this — see the tip above.
```

## Requirements

Python **3.9+**. The core install is pure-Python and depends only on pandas and
pyarrow, so `st.load()` works everywhere; the heavier extras are opt-in.
