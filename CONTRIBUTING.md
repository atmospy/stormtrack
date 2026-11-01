# Contributing to stormtrack

Thanks for helping! Bug reports, fixes, and features are all welcome via
[issues](https://github.com/syedhamidali/imdtrack/issues) and pull requests.

## Development setup ([uv](https://docs.astral.sh/uv/))

[uv](https://docs.astral.sh/uv/) is the fastest way to get a dev environment.
`uv sync` installs the **exact, locked** dependencies from `uv.lock` into `.venv`:

```bash
uv sync --extra dev --extra plot --extra docs   # everything, reproducibly
```

(Plain `pip` works too: `pip install -e ".[dev]"`.) The version is derived from
git tags by [hatch-vcs](https://github.com/ofek/hatch-vcs), so there's no
`__version__` to edit. If you change dependencies in `pyproject.toml`, refresh
the lock with `uv lock` and commit it.

## Checks

```bash
uv run pytest                     # tests (cartopy plot tests skip without cartopy)
uv run black . && uv run ruff check .   # format + lint
```

Install the pre-commit hooks so these run automatically:

```bash
uv pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Workflow

Never push to `main` directly. Create a branch, open a PR, and let CI (lint +
tests on Python 3.9–3.14 + docs build) go green before merging:

```bash
git switch -c my-change
# ... commit ...
git push -u origin my-change   # then open a PR
```

## Releases

Releases are cut from a git tag — no source edit. Tag `main` and push:

```bash
git tag v0.2.6 && git push origin v0.2.6
```

That triggers the release workflow (build → TestPyPI → PyPI → GitHub Release →
Zenodo). The dataset in `data/` also auto-updates monthly and cuts its own
patch release when IMD publishes new data.
