# API reference

```{eval-rst}
.. currentmodule:: stormtrack
```

## Loading data

```{eval-rst}
.. autofunction:: stormtrack.load
.. autofunction:: stormtrack.update
```

## The `BestTracks` bundle

```{eval-rst}
.. autoclass:: stormtrack.BestTracks
   :members:
   :undoc-members:
```

## IBTrACS, analysis and comparison

```{eval-rst}
.. autofunction:: stormtrack.load_ibtracs
.. autofunction:: stormtrack.fetch_ibtracs
.. autofunction:: stormtrack.build_ibtracs
.. autofunction:: stormtrack.compare_tracks
.. autoclass:: stormtrack.Comparison
   :members:
.. automodule:: stormtrack.analysis
   :members:
```

## Real-time data, verification and wind conversion

```{eval-rst}
.. automodule:: stormtrack.realtime
   :members:
.. automodule:: stormtrack.atcf
   :members:
.. automodule:: stormtrack.verification
   :members:
.. autofunction:: stormtrack.plot_forecast
```

## Pipeline (rebuild from the IMD workbook)

```{eval-rst}
.. autofunction:: stormtrack.build
.. autofunction:: stormtrack.parse_workbook
.. autofunction:: stormtrack.fetch_workbook
.. autofunction:: stormtrack.fetch_data_from_repo
```
