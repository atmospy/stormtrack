"""Sphinx configuration for the stormtrack documentation.

Docs are built with the PyData Sphinx Theme and MyST-NB, which executes the
example notebooks (authored as jupytext ``py:percent`` scripts) at build time.
So the rendered examples always reflect real, current output.
"""

from __future__ import annotations

import os
import pathlib

import stormtrack

# Execute the example notebooks against the dataset committed in the repo, with
# no network access.  Setting the env var here (before MyST-NB launches a
# kernel, which inherits this process's environment) makes ``st.load()`` inside
# the examples read ../data/ directly.
_DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
os.environ.setdefault("STORMTRACK_DATA_DIR", str(_DATA_DIR))

# -- Project information ----------------------------------------------------- #
project = "stormtrack"
author = "Hamid Ali Syed"
copyright = "2026, Hamid Ali Syed"
release = stormtrack.__version__
version = release

# -- General configuration --------------------------------------------------- #
extensions = [
    "myst_nb",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

# strip prompts so copied code is runnable
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

templates_path = ["_templates"]
# ``.py`` is registered as a notebook format below, so exclude this config file
# (and any build dir) from the document set — otherwise Sphinx tries to execute
# conf.py as a notebook.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "conf.py"]

# -- MyST / MyST-NB ---------------------------------------------------------- #
myst_enable_extensions = ["colon_fence", "deflist", "dollarmath"]

# Author examples as jupytext percent scripts (.py) and execute them.
nb_custom_formats = {".py": ["jupytext.reads", {"fmt": "py:percent"}]}
nb_execution_mode = "auto"
nb_execution_timeout = 180
nb_execution_raise_on_error = True  # a broken example fails the docs build

autosummary_generate = True
autodoc_typehints = "description"
napoleon_google_docstring = False
napoleon_numpy_docstring = True
# Render class "Attributes" as :ivar: fields, not separate object descriptions,
# to avoid "duplicate object description" warnings for dataclass fields.
napoleon_use_ivar = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "xarray": ("https://docs.xarray.dev/en/stable/", None),
}

# -- HTML output (PyData theme) ---------------------------------------------- #
html_theme = "pydata_sphinx_theme"
html_title = "stormtrack"
html_theme_options = {
    "github_url": "https://github.com/atmospy/stormtrack",
    "icon_links": [
        {
            "name": "PyPI",
            "url": "https://pypi.org/project/stormtrack/",
            "icon": "fa-brands fa-python",
        },
    ],
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "show_prev_next": False,
    "use_edit_page_button": True,
    "show_toc_level": 2,
}
html_context = {
    "github_user": "syedhamidali",
    "github_repo": "stormtrack",
    "github_version": "main",
    "doc_path": "docs",
}
