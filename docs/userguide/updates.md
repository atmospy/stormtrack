# Staying up to date

A [monthly GitHub Action](https://github.com/syedhamidali/imdtrack/blob/main/.github/workflows/update-dataset.yml)
re-fetches the IMD workbook and, **only if it parses and passes validation**,
updates the committed dataset — a broken upload can never overwrite the good
published data. You normally don't have to do anything:

```python
bt = st.load(update=True)      # pulls the latest (cheap conditional GET)
```

## How the pipeline works

1. Download the current IMD workbook and hash it. If it matches the published
   `manifest.json`, there's nothing to do.
2. Otherwise parse it and run validators (positions in range, expected columns
   present, record not shrinking, plausible year range, **completeness** — every
   positional row must be captured).
3. Only if **every** check passes are the parquet files replaced (atomically)
   and committed, the version tagged, and a release published. On any failure the
   job goes red and the committed dataset stays as it was.

## Running the pipeline yourself

```bash
stormtrack build                     # fetch IMD → parse → validate → write ./data
stormtrack info                      # summary of the current record
stormtrack export tracks.parquet     # dump observations to CSV/Parquet
```

Because the dataset is fetched from GitHub at runtime (not bundled in the
package), you always get the latest data via `st.load(update=True)` **without
upgrading** the pip/conda package.
