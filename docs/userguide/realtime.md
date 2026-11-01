# Real-time storms, forecasts & verification

`imdtrack.realtime` reads **ATCF** text decks (Sampson & Schrader 2000), the format NHC
and JTWC publish. Everything it returns uses the same columns as the archived
datasets, so [`imdtrack.analysis`](ibtracs.md) and the plots work on live storms too.

```python
import imdtrack as imd

now = imd.realtime.active_storms("jtwc", basins=["io"])    # JTWC North Indian Ocean
now.storms
fc = imd.realtime.get_forecast("AL042026")                  # NHC official forecast (OFCL)
gd = imd.realtime.get_guidance("AL042026")                  # every model, every cycle (a-deck)
```

## Which agencies?

| agency | best track (live) | forecast (live) |
|---|---|---|
| NHC / CPHC | `active_storms("nhc")` | `get_forecast(id)`, `get_guidance(id)` |
| JTWC | `active_storms("jtwc")` (open UCAR RAL mirror) | `get_forecast(id, source="jtwc")` — **mirrors may block automated access**; pass `url=` |
| IMD, JMA, BoM, Météo-France | archived only (`imd.load`, `imd.load_ibtracs`) | **no machine-readable feed found** |

IMD publishes its cyclone bulletins as text/PDF, not as a documented data feed, so
IMD's *forecasts* cannot be read programmatically; if that changes, parsing them into
the ATCF-style frame is all that is needed to plug them into the tools below.
Wind from NHC/JTWC is 1-minute sustained (kt); IMD's is 3-minute (see the warning in
[IBTrACS & analysis](ibtracs.md)).

## Verifying forecasts

Score any forecast against any best track — including NHC or JTWC forecasts of a North
Indian Ocean storm against the IMD record:

```python
from imdtrack import verification as V

errors = V.forecast_errors(gd, best_track)        # track, along/cross-track, wind, pressure
V.error_summary(errors)                           # by technique and lead time
radii = V.error_radii(errors[errors.tech == "OFCL"], pct=67, units="nm")
```

Following NHC practice, a forecast counts only if the system was a tropical or
subtropical cyclone at both the forecast and the verifying time (when the best track
has a storm type), and the best track is interpolated to the verifying time.
`along_km` is positive when the forecast is *ahead* of the best-track motion, `cross_km`
positive to its right.

## The forecast cone

NHC's cone is the area swept by circles at each forecast point whose radii contain
two-thirds of the previous five years' official track errors. `error_radii(pct=67)`
reproduces that definition from *your* errors, and `cone_polygons` / `plot_forecast`
draw it:

```python
imd.plot_forecast(fc, best=track_so_far, radii_km=radii)
```

`plot_forecast` colours the forecast (and best-track) points by intensity category and
labels every 24 h with lead time, wind and category. `scale="saffir-simpson"` (default;
TD, TS, C1–C5, matching the 1-minute winds of NHC/JTWC) or `scale="imd"` (IMD grades from
the wind — approximate for non-IMD winds).

NHC announced an experimental ellipse-based cone (90th percentile, separate along- and
cross-track axes) for 2026; only the circle definition is implemented. The cone covers
track error only — not intensity, size or hazards.

## Forecast intensity and ACE

`interpolate_forecast(fc, step=6)` linearly interpolates a forecast to 6-hourly steps,
so `analysis.ace` (on a frame with `storm_id` and `wind`) gives forecast ACE.

## Acknowledgment

The design of the real-time layer (ATCF b-deck/f-deck handling, a recency filter for
active storms, plausibility bounds on wind and pressure, 6-hourly forecast interpolation)
was informed by reading the [tropycal](https://github.com/tropycal/tropycal) source and
docs. This is an independent implementation; the definitions it relies on are
referenced to the literature in [References](../references.md).
