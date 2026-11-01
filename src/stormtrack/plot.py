"""Publication-quality Cartopy plots for IMD cyclone tracks (optional ``plot`` extra).

Inspired by `tropycal <https://tropycal.github.io/>`_ but coloured by **IMD grade**
rather than Saffir–Simpson. Cartopy/matplotlib are imported lazily inside the
functions, so ``import stormtrack`` works even without them — calling a plot then
raises a clear ``pip install stormtrack[plot]`` message.

Examples
--------
>>> import stormtrack as st
>>> bt = st.load()
>>> st.plot_track(bt.storm("tauktae"), color="grade")      # by IMD category
>>> st.plot_track(bt.storm("2020-001"), color="wind")      # by wind speed
>>> st.plot_tracks(bt.observations, color="basin")         # every track
"""

from __future__ import annotations

from ._schema import GRADE_LONG, GRADE_ORDER

# IMD grade -> colour: a calm→intense ramp (blue depression → dark-red super cyclone).
GRADE_COLORS = {
    "D": "#8ecae6",
    "DD": "#52b788",
    "CS": "#ffd166",
    "SCS": "#f8961e",
    "VSCS": "#f3722c",
    "ESCS": "#d62828",
    "SuCS": "#6a040f",
}
BASIN_COLORS = {"BOB": "#2a78d6", "ARB": "#eb6834", "LAND": "#9aa0a6", "NI": "#6a4c93"}

# chrome
_OCEAN = "#eaf2fb"
_LAND = "#f1eee7"
_COAST = "#7d7d7d"
_BORDER = "#c4c4c4"
_INK = "#1a1a1a"


def _cartopy():
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - only hit without cartopy
        raise ImportError(
            "Map plotting needs cartopy and matplotlib. Install them with:\n"
            "    pip install 'stormtrack[plot]'          # needs Python <= 3.13\n"
            "    conda install -c conda-forge stormtrack  # bundles a prebuilt cartopy"
        ) from exc
    return ccrs, cfeature, plt


def _basemap(ax, extent, ccrs, cfeature, label_size=8, crs=None, lon_ticks=None):
    ax.set_extent(extent, crs=crs or ccrs.PlateCarree())
    ax.add_feature(cfeature.OCEAN.with_scale("50m"), facecolor=_OCEAN, zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor=_LAND, zorder=0)
    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), linewidth=0.6, edgecolor=_COAST, zorder=1)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.4, edgecolor=_BORDER, zorder=1)
    gl = ax.gridlines(
        draw_labels=True, linewidth=0.4, color="#c9c9c9", alpha=0.7, linestyle=(0, (1, 3))
    )
    gl.top_labels = gl.right_labels = False
    gl.xlabel_style = gl.ylabel_style = {"size": label_size, "color": "#666"}
    if lon_ticks is not None:  # explicit longitudes (needed on a dateline-centred map)
        import matplotlib.ticker as mticker
        from cartopy.mpl.ticker import LongitudeFormatter

        gl.xlocator = mticker.FixedLocator(lon_ticks)
        gl.xformatter = LongitudeFormatter()


def _extent(lon, lat, pad):
    return [
        float(lon.min()) - pad,
        float(lon.max()) + pad,
        float(lat.min()) - pad,
        float(lat.max()) + pad,
    ]


def _new_fig(extent, base, plt, ccrs):
    """A figure sized to the map's aspect so a fixed-aspect GeoAxes fills it."""
    w = max(extent[1] - extent[0], 1e-6)
    h = max(extent[3] - extent[2], 1e-6)
    figh = max(3.5, min(11.0, base * (h / w) + 1.2))
    fig = plt.figure(figsize=(base, figh), layout="constrained")
    ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    return fig, ax


def _peak_idx(t):
    return t["wind"].idxmax() if t["wind"].notna().any() else None


def _auto_title(t):
    """A two-line title from the storm's own data, e.g.::

    Cyclone Tauktae (2021)
    Peak: ESCS · 100 kt

    Defensive: works on any track frame, falling back gracefully when the name,
    id, year, or intensity columns are missing.
    """
    year = int(t["time"].dt.year.iloc[0]) if "time" in t.columns else None
    name = None
    if "name" in t.columns and t["name"].notna().any():
        name = str(t["name"].dropna().iloc[0]).title()
    if name:
        label = f"Cyclone {name}"
    elif "storm_id" in t.columns:
        label = str(t["storm_id"].iloc[0])
    else:
        label = "Cyclone track"
    head = f"{label} ({year})" if year else label
    if "wind" in t.columns and t["wind"].notna().any():
        grade = t["grade"].max() if "grade" in t.columns else float("nan")
        gtxt = f"{grade} · " if grade == grade else ""  # skip if NaN
        head += f"\nPeak: {gtxt}{t['wind'].max():.0f} kt"
    return head


def _halo():
    import matplotlib.patheffects as pe

    return [pe.withStroke(linewidth=2.4, foreground="white")]


def _colored_line(ax, t, color, cmap, pc):
    """Draw the track as intensity-coloured segments; return a mappable or None."""
    import numpy as np
    from matplotlib.collections import LineCollection

    pts = np.column_stack([t["lon"].to_numpy(), t["lat"].to_numpy()]).reshape(-1, 1, 2)
    if len(pts) < 2:
        ax.plot(t["lon"], t["lat"], color="0.5", transform=pc, zorder=3)
        return None
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)

    # a white casing under the coloured line makes it read cleanly over coastlines
    casing = LineCollection(
        segs, colors="white", linewidths=5.2, transform=pc, zorder=3, capstyle="round"
    )
    ax.add_collection(casing)

    if color == "wind":
        from matplotlib.colors import Normalize

        w = t["wind"].to_numpy(dtype="float64")
        finite = w[np.isfinite(w)]
        vmin = float(finite.min()) if finite.size else 20.0
        vmax = float(finite.max()) if finite.size else 120.0
        lc = LineCollection(
            segs,
            cmap=cmap,
            norm=Normalize(vmin, vmax),
            transform=pc,
            linewidths=3.4,
            zorder=4,
            capstyle="round",
        )
        lc.set_array(w[:-1])
        ax.add_collection(lc)
        return lc

    seg_colors = [GRADE_COLORS.get(str(g), "#999999") for g in t["grade"].astype(object)[:-1]]
    lc = LineCollection(
        segs, colors=seg_colors, transform=pc, linewidths=3.4, zorder=4, capstyle="round"
    )
    ax.add_collection(lc)
    return None


def plot_track(
    track,
    ax=None,
    color="grade",
    cmap="viridis",
    extent=None,
    pad=2.0,
    show_start=True,
    show_end=True,
    show_peak=True,
    annotate=False,
    title=None,
):
    """Plot one storm's track on a Cartopy map, as intensity-coloured segments.

    Parameters
    ----------
    track : DataFrame for a single storm (e.g. ``bt.storm(id_or_name)``) with
            ``lat``, ``lon``, ``time`` and, for colouring, ``grade`` or ``wind``.
    color : ``"grade"`` (IMD category, discrete legend) or ``"wind"`` (colorbar).
    cmap  : colormap used when ``color="wind"``.
    show_start, show_end, show_peak : mark genesis (●), dissipation (✖) and the
            lifetime-peak (★) fixes.
    annotate : label those markers (peak includes its wind speed).
    title : your own title string; ``""`` for none. If left as ``None`` a
            two-line title is generated from the storm — e.g.
            ``"Cyclone Tauktae (2021)\\nPeak: ESCS · 100 kt"``.
    """
    ccrs, cfeature, plt = _cartopy()
    from matplotlib.lines import Line2D

    t = track.sort_values("time").reset_index(drop=True)
    ext = extent or _extent(t["lon"], t["lat"], pad)
    if ax is None:
        _, ax = _new_fig(ext, 7.5, plt, ccrs)
    _basemap(ax, ext, ccrs, cfeature)
    pc = ccrs.PlateCarree()

    mappable = _colored_line(ax, t, color, cmap, pc)
    if mappable is not None:
        cb = ax.figure.colorbar(mappable, ax=ax, shrink=0.72, pad=0.02)
        cb.set_label("Max sustained wind (kt)", color=_INK)
        cb.outline.set_visible(False)
        cb.ax.tick_params(color="#999", labelcolor="#555")

    def _mark(i, marker, size, face, label):
        ax.scatter(
            t["lon"].iloc[i],
            t["lat"].iloc[i],
            marker=marker,
            s=size,
            facecolor=face,
            edgecolor="black",
            linewidth=0.8,
            transform=pc,
            zorder=6,
        )
        if annotate:
            ax.annotate(
                label,
                (t["lon"].iloc[i], t["lat"].iloc[i]),
                xytext=(7, 7),
                textcoords="offset points",
                fontsize=8.5,
                fontweight="bold",
                color=_INK,
                zorder=7,
                path_effects=_halo(),
            )

    pk = _peak_idx(t)
    if show_start:
        _mark(0, "o", 80, "#2ca02c", "start")
    if show_end:
        _mark(len(t) - 1, "X", 95, "#d62828", "end")
    if show_peak and pk is not None:
        pos = int(t.index.get_loc(pk))
        _mark(pos, "*", 260, "#ffcf33", f"peak {t['wind'].iloc[pos]:.0f} kt")

    handles = []
    if color == "grade":
        present = [g for g in GRADE_ORDER if g in set(t["grade"].dropna().astype(object))]
        handles += [
            Line2D([], [], color=GRADE_COLORS[g], lw=3, label=f"{g} · {GRADE_LONG[g]}")
            for g in present
        ]
    marks = []
    if show_start:
        marks.append(Line2D([], [], marker="o", ls="", mfc="#2ca02c", mec="black", label="genesis"))
    if show_peak and pk is not None:
        marks.append(
            Line2D(
                [], [], marker="*", ls="", mfc="#ffcf33", mec="black", markersize=12, label="peak"
            )
        )
    if show_end:
        marks.append(Line2D([], [], marker="X", ls="", mfc="#d62828", mec="black", label="end"))
    if handles or marks:
        ax.legend(
            handles=handles + marks,
            loc="upper right",
            fontsize=8,
            framealpha=0.92,
            edgecolor="#dddddd",
        ).set_zorder(8)

    title = _auto_title(t) if title is None else title
    _set_title(ax, title)
    return ax


def _set_title(ax, title):
    # A fixed-aspect GeoAxes can fill the figure, leaving no room for ax.set_title
    # under constrained_layout; suptitle reserves space reliably. Only when we own
    # the whole figure (single map) — otherwise fall back to a normal axes title.
    if not title:
        return
    fig = ax.figure
    if len(fig.axes) <= 2:  # the map (+ optional colorbar)
        fig.suptitle(title, fontsize=12.5, fontweight="bold", color=_INK, linespacing=1.4)
    else:
        ax.set_title(title, fontsize=12.5, fontweight="bold", color=_INK, linespacing=1.4)


def plot_tracks(
    observations, ax=None, color="basin", extent=None, pad=1.0, linewidth=1.1, alpha=0.6, title=None
):
    """Plot many tracks on one map (e.g. ``bt.observations``), coloured by
    ``"basin"`` (default) or by each storm's peak ``"grade"``."""
    ccrs, cfeature, plt = _cartopy()
    from matplotlib.lines import Line2D

    obs = observations
    ext = extent or _extent(obs["lon"], obs["lat"], pad)
    if ax is None:
        _, ax = _new_fig(ext, 9.0, plt, ccrs)
    _basemap(ax, ext, ccrs, cfeature)
    pc = ccrs.PlateCarree()

    peak = None
    if color == "grade":
        rank = {g: i for i, g in enumerate(GRADE_ORDER)}
        peak = (
            obs.assign(_r=obs["grade"].astype(object).map(rank))
            .sort_values("_r")
            .groupby("storm_id", sort=False)
            .last()["grade"]
        )
    for sid, g in obs.groupby("storm_id", sort=False):
        if color == "grade":
            c = GRADE_COLORS.get(str(peak.get(sid)), "#999999")
        else:
            c = BASIN_COLORS.get(str(g["basin"].iloc[0]), "#9aa0a6")
        ax.plot(
            g["lon"],
            g["lat"],
            color=c,
            linewidth=linewidth,
            alpha=alpha,
            solid_capstyle="round",
            transform=pc,
            zorder=3,
        )

    if color == "basin":
        keys = [b for b in ("BOB", "ARB", "LAND", "NI") if b in set(obs["basin"].astype(object))]
        handles = [Line2D([], [], color=BASIN_COLORS[b], lw=2.5, label=b) for b in keys]
        ttl = "Sub-basin"
    else:
        present = set(peak.dropna().astype(object)) if peak is not None else set()
        keys = [g for g in GRADE_ORDER if g in present]
        handles = [Line2D([], [], color=GRADE_COLORS[g], lw=2.5, label=g) for g in keys]
        ttl = "Peak grade"
    if handles:
        ax.legend(
            handles=handles,
            loc="upper right",
            fontsize=8,
            title=ttl,
            framealpha=0.92,
            edgecolor="#dddddd",
        ).set_zorder(8)

    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color=_INK)
    return ax


# Saffir-Simpson hurricane wind scale (1-min wind, kt) - colours chosen to read on a pale map.
SS_CATEGORIES = [("TD", 0, "#7fb2e5"), ("TS", 34, "#2bb673"), ("C1", 64, "#f2c744"),
                 ("C2", 83, "#f5a03a"), ("C3", 96, "#ec6a2c"), ("C4", 113, "#d62828"),
                 ("C5", 137, "#8b1a6b")]  # fmt: skip
SS_LONG = {"TD": "Tropical depression", "TS": "Tropical storm"}
SS_LONG.update({f"C{i}": f"Category {i}" for i in range(1, 6)})


def _category(wind, scale):
    """Category label and colour for each wind (kt): ``("TS", "#2bb673")``; ``(None, grey)``
    for missing wind. ``scale`` is ``"saffir-simpson"`` or ``"imd"`` (IMD grades)."""
    import numpy as np

    w = np.asarray(wind, dtype=float)
    if scale == "imd":
        from .analysis import grade_from_wind

        g = grade_from_wind(w).astype(object)
        return [(x, GRADE_COLORS[x]) if isinstance(x, str) else (None, "#999999") for x in g]
    bounds = [b for _, b, _ in SS_CATEGORIES]
    out = []
    for v in w:
        if not np.isfinite(v):
            out.append((None, "#999999"))
            continue
        name, _, col = SS_CATEGORIES[max(np.searchsorted(bounds, v, side="right") - 1, 0)]
        out.append((name, col))
    return out


def plot_forecast(
    forecast, best=None, radii_km=None, ax=None, extent=None, title=None, scale="saffir-simpson"
):
    """Map of an official forecast, optionally with the track so far and its cone.

    Every 24 h the forecast point is labelled with its lead time, wind (kt) and category.
    The legend sits below the map (when ``ax`` is not given), so it never covers data.

    Parameters
    ----------
    forecast : an ATCF forecast frame (``stormtrack.realtime.get_forecast``).
    best : the storm's track so far (``bt.storm(...)`` or ``active_storms(...).storm(...)``),
           drawn as the observed (best) track, its dots coloured by intensity.
    radii_km : lead time (h) -> circle radius (km), e.g. ``verification.error_radii``;
           draws the cone of uncertainty (union of circles swept along the track).
    scale : how points are coloured and labelled by intensity category — ``"saffir-simpson"``
           (default; TD, TS, C1–C5, suited to NHC/JTWC 1-minute winds) or ``"imd"`` (IMD
           grades D … SuCS from the wind, approximate for non-IMD winds).
    """
    ccrs, cfeature, plt = _cartopy()
    import math

    import numpy as np
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon

    from .verification import cone_polygons

    f = forecast.sort_values("tau").reset_index(drop=True)
    polys = cone_polygons(f, radii_km) if radii_km is not None else []  # unwrapped longitudes
    # draw in one continuous longitude frame so tracks crossing the dateline stay whole
    f["lon"] = np.degrees(np.unwrap(np.radians(f["lon"].to_numpy())))
    lon0 = float(f["lon"].iloc[0])
    cats = _category(f["vmax"], scale)
    b = best.sort_values("time").copy() if best is not None else None
    if b is not None:  # bring the best track into the forecast's longitude frame
        b["lon"] = lon0 + (b["lon"].to_numpy(dtype=float) - lon0 + 180) % 360 - 180
    bcats = []
    if b is not None:
        bw = b["wind"] if "wind" in b else b.get("vmax", [np.nan] * len(b))
        bcats = _category(bw, scale)

    # legend entries, known up front so the figure can reserve room for them
    handles = []
    if b is not None:
        handles.append(Line2D([], [], color=_INK, lw=1.8, label="observed track (best track)"))
    handles.append(Line2D([], [], color="#a61e1e", ls="--", label=f"{f['tech'].iloc[0]} forecast"))
    if polys:
        handles.append(Patch(fc="#f7d9d6", ec="#c0504d", label="cone of uncertainty"))
    seen = {n: c for n, c in cats + bcats if n}
    order = [n for n, _, _ in SS_CATEGORIES] if scale != "imd" else GRADE_ORDER
    longn = SS_LONG if scale != "imd" else GRADE_LONG
    handles += [
        Line2D([], [], marker="o", ls="", mfc=seen[n], mec="#4a0d0d", ms=9, label=longn[n])
        for n in order
        if n in seen
    ]
    ncol = min(3, len(handles))
    rows = math.ceil(len(handles) / ncol)

    xs = [f["lon"].to_numpy()] + [p[:, 0] for p in polys]
    ys = [f["lat"].to_numpy()] + [p[:, 1] for p in polys]
    if b is not None:
        xs.append(b["lon"].to_numpy())
        ys.append(b["lat"].to_numpy())
    x, y = np.concatenate(xs), np.concatenate(ys)
    if extent is None:  # a small margin, with a sane minimum size and aspect
        w, h = max(x.max() - x.min(), 6.0), max(y.max() - y.min(), 4.0)
        h = max(h, w / 1.7)
        w = max(w, h / 1.6)
        cx, cy = (x.max() + x.min()) / 2, (y.max() + y.min()) / 2
        extent = [cx - w * 0.58, cx + w * 0.58, cy - h * 0.58, cy + h * 0.58]

    own_fig = ax is None
    if own_fig:
        # place the axes by hand, in inches, so the map exactly fills its box: no side
        # margins; room only for the title above, tick labels left / below, legend under
        figw, ml, mr, mt = 8.0, 0.9, 0.35, 0.65
        mb = 0.6 + 0.32 * rows + 0.12
        maph = (figw - ml - mr) * (extent[3] - extent[2]) / (extent[1] - extent[0])
        figh = maph + mb + mt
        fig = plt.figure(figsize=(figw, figh))
        # a map that straddles the dateline is centred on it; data keep their (unwrapped)
        # longitudes and are transformed from plain PlateCarree
        centre = 180 if (extent[1] > 180 or extent[0] < -180) else 0
        ax = fig.add_axes([ml / figw, mb / figh, (figw - ml - mr) / figw, maph / figh],
                          projection=ccrs.PlateCarree(central_longitude=centre))  # fmt: skip
    pc = ccrs.PlateCarree()
    shift = ax.projection.proj4_params.get("lon_0", 0) if hasattr(ax, "projection") else 0
    if shift:  # extent given in the axes' own (dateline-centred) coordinates
        x0 = extent[0] % 360 - 180
        ext = [x0, x0 + (extent[1] - extent[0]), extent[2], extent[3]]
        span = extent[1] - extent[0]
        step = next((t for t in (20, 10, 5, 2, 1) if span / t >= 3), 1)  # >= 3 ticks
        first = math.ceil(extent[0] / step) * step
        ticks = [((v + 180) % 360) - 180 for v in np.arange(first, extent[1] + 1e-6, step)]
        _basemap(ax, ext, ccrs, cfeature, label_size=11, crs=ax.projection, lon_ticks=ticks)
    else:
        _basemap(ax, extent, ccrs, cfeature, label_size=11)

    # cone: dark rim underneath, light fill on top -> an outline of the union only
    for p in polys:
        ax.add_patch(Polygon(p, fc="#c0504d", ec="#c0504d", lw=1.8, transform=pc, zorder=0.7))
    for p in polys:
        ax.add_patch(Polygon(p, fc="#f7d9d6", ec="#f7d9d6", lw=0.8, transform=pc, zorder=0.8))

    if b is not None:
        ax.plot(b["lon"], b["lat"], "-", color=_INK, lw=1.8, transform=pc, zorder=4)
        ax.scatter(b["lon"], b["lat"], s=34, c=[c for _, c in bcats], edgecolor=_INK, lw=0.8,
                   transform=pc, zorder=5)  # fmt: skip
    ax.plot(f["lon"], f["lat"], "--", color="#a61e1e", lw=1.4, transform=pc, zorder=5)
    ax.scatter(f["lon"], f["lat"], s=95, c=[c for _, c in cats], edgecolor="#4a0d0d", lw=1.0,
               transform=pc, zorder=6)  # fmt: skip

    # labels every 24 h, centred above/below the marker (or beside it on steep tracks),
    # alternating sides so neighbours don't collide
    lat, lon = f["lat"].to_numpy(), f["lon"].to_numpy()
    tau = f["tau"].to_numpy()
    for k, i in enumerate(np.flatnonzero((tau % 24 == 0) & (tau > 0))):
        j0, j1 = max(i - 1, 0), min(i + 1, len(f) - 1)
        dx = (lon[j1] - lon[j0]) * np.cos(np.radians(lat[i]))
        dy = lat[j1] - lat[j0]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n  # unit normal, left of travel
        if (ny < 0 or (ny == 0 and nx < 0)) == (k % 2 == 0):
            nx, ny = -nx, -ny
        vertical = abs(ny) >= abs(nx)
        ha = "center" if vertical else ("left" if nx > 0 else "right")
        va = ("bottom" if ny > 0 else "top") if vertical else "center"
        dist = 15
        wind = f["vmax"].iloc[i]
        txt = f"+{int(tau[i])} h"
        if np.isfinite(wind):
            txt += f"\n{wind:.0f} kt" + (f" · {cats[i][0]}" if cats[i][0] else "")
        ax.annotate(txt, (lon[i], lat[i]), xytext=(nx * dist, ny * dist),
                    textcoords="offset points", ha=ha, va=va, fontsize=11.5,
                    fontweight="bold", color=_INK, path_effects=_halo(), zorder=7,
                    xycoords=pc._as_mpl_transform(ax), linespacing=1.15)  # fmt: skip

    if own_fig:
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=ncol,
                   fontsize=11, frameon=False, columnspacing=1.6, handlelength=1.8)  # fmt: skip
    else:
        ax.legend(handles=handles, loc="best", fontsize=10, framealpha=0.92,
                  edgecolor="#dddddd").set_zorder(8)  # fmt: skip

    if title is None:
        name = f["name"].dropna().iloc[-1] if "name" in f and f["name"].notna().any() else None
        who = f"{name.title()} ({f['atcf_id'].iloc[0]})" if name else f["atcf_id"].iloc[0]
        title = f"{who} — {f['tech'].iloc[0]} forecast from {f['init'].iloc[0]:%d %b %Y %H}Z"
    if title:
        ax.set_title(title, fontsize=14.5, fontweight="bold", color=_INK)
    return ax
