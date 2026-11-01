# IBTrACS & cross-dataset analysis

`imdtrack` can load [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)
into the same tidy schema as the IMD record, so analysis code is written once and
runs on either dataset.

## Loading

```python
import imdtrack as imd

ib = imd.load_ibtracs()                          # published North Indian Ocean dataset
ib = imd.load_ibtracs(since=1982, basin="NI")    # filter by season / genesis basin
wp = imd.load_ibtracs(basin="WP", source="ncei") # other basins: download from NOAA/NCEI
ib = imd.load_ibtracs(path="ibtracs.ALL.list.v04r01.csv", basin="NI")  # a local CSV
```

The NI dataset lives in the repo under `data/ibtracs/` (`observations.parquet`,
`storms.parquet`, `manifest.json`). `imdtrack build-ibtracs` rebuilds it from NCEI:
the download is hashed, skipped if unchanged, validated, and only then written
atomically. The monthly workflow runs it alongside the IMD build.

Beyond the shared columns (`storm_id, year, basin, name, time, lat, lon, wind,
pressure, grade, step`) IBTrACS frames carry `wmo_wind`, `usa_wind`, `wind_agency`,
`sshs`, `dist2land`, `storm_speed`, `nature`, `track_type` and `imd_*` (IMD's own
submission to IBTrACS). `wind` is the WMO-agency wind filled with the JTWC wind.

```{warning}
Agencies average wind over different periods (IMD 3-min, NHC/JTWC 1-min, JMA
10-min). WMO/TD-1555 (Harper et al. 2010) gives conversions only between 1-min and
10-min winds (`analysis.convert_vmax`); there is none for 3-min. Compare intensities across agencies with care.
```

## Analysis (`imdtrack.analysis`)

| function | gives |
|---|---|
| `lifetime_max` | per-storm peak wind, time/place, genesis point, duration |
| `intensity_change`, `rapid_intensification` | N-hour wind change; RI (≥30 kt/24 h) events |
| `annual_counts`, `monthly_climatology` | counts by strength class per year / month |
| `ace` | accumulated cyclone energy |
| `translation_speed` | speed and heading between fixes |
| `match_controls` | matched control storms (same basin, similar peak wind, nearest year) |
| `storm_windows` | pre / during / post timeline per storm, for lifecycle composites with gridded data |
| `paired_bootstrap` | mean paired difference with bootstrap confidence interval |

The last three are the building blocks of event-vs-control composite studies, for
example environmental response around storms with extreme cloud tops.

## Comparing IMD with IBTrACS

```python
cmp = imd.compare_tracks(imd.load(), imd.load_ibtracs())
cmp.matches      # one row per paired storm (ids, names, peak wind difference, timing)
cmp.fixes        # every common fix: position error (km), wind and pressure differences
cmp.summary()    # bias / MAE / RMSE / correlation
cmp.unmatched_a, cmp.unmatched_b
```

Storms are paired by *track* (shared times and proximity), not by name, because older
IMD systems are unnamed. Choose the IBTrACS intensity with `ib_wind` (`"usa"`, `"wmo"`,
`"imd"`, `"merged"`) and rescale with `ib_wind_scale`.
