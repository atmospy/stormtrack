# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.0
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Quickstart
#
# This example loads the IMD best-track record, explores the tidy tables, plots a
# cyclone track, and shows the xarray view. It runs end-to-end when the docs are
# built, so every output below is real.

# %%
import stormtrack as st

bt = st.load()
bt

# %% [markdown]
# ## The tidy `observations` frame
#
# One row per 3-hourly fix, with a stable `storm_id` (`"<year>-<serial>"`).

# %%
bt.observations.head()

# %% [markdown]
# ## Storm-level summary
#
# One row per storm: peak grade, max wind, min pressure, start/end time.

# %%
bt.storms.tail()

# %% [markdown]
# ## Plot a cyclone track
#
# The optional `[plot]` extra (`pip install stormtrack[plot]`) draws
# publication-quality Cartopy maps — the track is coloured by **IMD category**,
# with genesis/peak/end marked. Look storms up by id **or name**:

# %%
st.plot_track(bt.storm("tauktae"), color="grade", annotate=True)

# %% [markdown]
# …or colour by wind speed instead (the title is generated from the storm):

# %%
st.plot_track(bt.storm("2020-001"), color="wind")

# %% [markdown]
# ## The xarray Dataset
#
# A ragged track becomes a 2-D `(storm, step)` grid, IBTrACS-style.

# %%
ds = bt.to_xarray()
ds

# %% [markdown]
# Slice one storm and get its peak intensity:

# %%
ds.sel(storm="2020-001")["wind"].max().item()

# %% [markdown]
# ## Data quality
#
# The dataset mirrors the IMD workbook faithfully, including its occasional
# data-entry errors, which are flagged **non-destructively**: `pos_suspect` marks
# fixes whose coordinates imply an impossible jump, and `date_suspect` marks
# day/month-transposed dates. Inspect them, or clean them on demand:

# %%
flagged = bt.observations.query("pos_suspect or date_suspect")
print(
    f"{len(flagged)} flagged fixes "
    f"({int(bt.observations['pos_suspect'].sum())} position, "
    f"{int(bt.observations['date_suspect'].sum())} date)"
)

# %%
# Drop the coordinate spikes and swap day/month-transposed dates back into order.
clean = st.load().clean(fix_dates=True)
clean
