# API reference

```{eval-rst}
.. currentmodule:: imdtrack
```

## Loading data

```{eval-rst}
.. autofunction:: imdtrack.load
.. autofunction:: imdtrack.update
```

## The `BestTracks` bundle

```{eval-rst}
.. autoclass:: imdtrack.BestTracks
   :members:
   :undoc-members:
```

## IBTrACS, analysis and comparison

```{eval-rst}
.. autofunction:: imdtrack.load_ibtracs
.. autofunction:: imdtrack.fetch_ibtracs
.. autofunction:: imdtrack.build_ibtracs
.. autofunction:: imdtrack.compare_tracks
.. autoclass:: imdtrack.Comparison
   :members:
.. automodule:: imdtrack.analysis
   :members:
```

## Real-time data, verification and wind conversion

```{eval-rst}
.. automodule:: imdtrack.realtime
   :members:
.. automodule:: imdtrack.atcf
   :members:
.. automodule:: imdtrack.verification
   :members:
.. autofunction:: imdtrack.plot_forecast
```

## Pipeline (rebuild from the IMD workbook)

```{eval-rst}
.. autofunction:: imdtrack.build
.. autofunction:: imdtrack.parse_workbook
.. autofunction:: imdtrack.fetch_workbook
.. autofunction:: imdtrack.fetch_data_from_repo
```
