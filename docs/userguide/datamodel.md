# The data model

A parsed record is a {class}`~stormtrack.BestTracks` bundle of three frames:
`observations` (one row per fix), `storms` (one row per storm), and `remarks`
(free-text notes).

## The tidy `observations` frame

| column | meaning |
|---|---|
| `storm_id` | stable id, `"<year>-<serial>"` e.g. `2020-001` |
| `year`, `serial` | year and IMD serial number of the system |
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
| `pos_suspect`, `date_suspect` | QC flags (see {doc}`quality`) |

## The xarray Dataset

Laid out like [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive):
a ragged track becomes a 2-D `(storm, step)` grid. Per-fix variables span both
dims; storm-level metadata (`name`, `basin`, `year`, …) are `storm` coordinates.

```python
ds = bt.to_xarray()
ds.sel(storm="2020-001")["wind"].max()      # Amphan peak intensity
ds.where(ds.basin == "ARB", drop=True)      # Arabian Sea storms only
```

## IMD intensity grades

| grade | name | sustained wind |
|---|---|---|
| `D` | Depression | 17–27 kt |
| `DD` | Deep Depression | 28–33 kt |
| `CS` | Cyclonic Storm | 34–47 kt |
| `SCS` | Severe Cyclonic Storm | 48–63 kt |
| `VSCS` | Very Severe Cyclonic Storm | 64–89 kt |
| `ESCS` | Extremely Severe Cyclonic Storm | 90–119 kt |
| `SuCS` | Super Cyclonic Storm | ≥ 120 kt |
