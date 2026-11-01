# Data quality

`stormtrack` mirrors the IMD workbook faithfully, including its occasional
data-entry errors. Two conservative, **non-destructive** checks flag them — the
source values are never altered:

- **`pos_suspect`** — a fix whose coordinates imply an impossible jump (an
  isolated position spike), e.g. a corrupted latitude.
- **`date_suspect`** — a day/month-transposed date, e.g. Nargis (2008) where
  May 1–3 were stored as "01/05, 02/05, 03/05" (Jan/Feb/Mar 5), scattering the
  storm across months.

```python
bt = st.load()
bt.observations.query("pos_suspect or date_suspect")   # inspect flagged fixes
```

## Cleaning on demand

{meth}`~stormtrack.BestTracks.clean` returns a cleaned copy — the source is left
untouched:

```python
bt.clean()                       # drop position spikes
bt.clean(how="mask")             # keep the rows but null lat/lon
bt.clean(fix_dates=True)         # also swap day/month back and re-order the track
```

These catch the common, well-defined cases; a few storms have messier date
corruption that is left as-is (visible as an implausibly long
`start_time`–`end_time` span).

## Caveats

- Data © India Meteorological Department. This library only reformats it; verify
  against IMD for operational use. The most recent season is *tentative* until
  IMD's post-season review.
- Older years often lack storm names and some fields (e.g. central pressure);
  those appear as `NaN`.
