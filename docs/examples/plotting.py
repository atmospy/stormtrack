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
# # Track plotting gallery
#
# The optional `[plot]` extra (`pip install stormtrack[plot]`) adds Cartopy maps
# via `st.plot_track` (one storm) and `st.plot_tracks` (many). Tracks are drawn
# as intensity-coloured lines over a clean basemap — tropycal-style, but using
# **IMD grades**. Everything below runs on the committed dataset.

# %%
import stormtrack as st

bt = st.load().clean(fix_dates=True)

# %% [markdown]
# ## A single track, coloured by IMD category
#
# Storms can be looked up by `storm_id` **or name** (case-insensitive). Genesis
# (●), lifetime peak (★) and dissipation (✖) are marked; `annotate=True` labels
# them.

# %%
st.plot_track(bt.storm("tauktae"), color="grade", annotate=True)

# %% [markdown]
# ## …or coloured by wind speed
#
# The strongest storm on record — the 1999 Odisha super cyclone (140 kt). Pass
# `extent=[lon0, lon1, lat0, lat1]` to frame the whole basin (rather than
# auto-fitting the track) and `title="…"` for your own title.

# %%
strongest = bt.storms.loc[bt.storms["max_wind"].idxmax(), "storm_id"]
st.plot_track(
    bt.storm(strongest),
    color="wind",
    cmap="turbo",
    extent=[60, 100, 0, 40],
    title="Strongest on record",
)

# %% [markdown]
# ## Every track on one map, by sub-basin
#
# `plot_tracks` overlays the whole archive; colour by `"basin"` (Bay of Bengal
# vs Arabian Sea) …

# %%
st.plot_tracks(bt.observations, color="basin", title="North Indian Ocean best tracks, 1982–present")

# %% [markdown]
# ## … or by each storm's peak intensity

# %%
st.plot_tracks(bt.observations, color="grade", title="Tracks by peak IMD grade")

# %% [markdown]
# Both functions accept an existing Cartopy `ax` (pass `ax=...`) and an `extent`
# `[lon0, lon1, lat0, lat1]`, so you can compose them into multi-panel figures or
# zoom to a region.
