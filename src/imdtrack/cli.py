"""Command-line interface: ``imdtrack update`` / ``info`` / ``export`` / ``build``."""

from __future__ import annotations

import argparse
import sys

from .core import load


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="imdtrack", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_up = sub.add_parser("update", help="Refresh the published dataset from GitHub (if changed).")
    p_up.add_argument(
        "--source",
        choices=["github", "imd"],
        default="github",
        help="github (default): pull the pre-parsed dataset; imd: parse the workbook.",
    )
    p_up.add_argument("--force", action="store_true", help="Re-download even if unchanged.")

    p_info = sub.add_parser("info", help="Show a summary of the cached record.")
    p_info.add_argument("--source", choices=["github", "imd"], default="github")

    p_ex = sub.add_parser("export", help="Export the observations table to CSV/Parquet.")
    p_ex.add_argument("out", help="Output path (.csv or .parquet).")
    p_ex.add_argument("--source", choices=["github", "imd"], default="github")
    p_ex.add_argument("--update", action="store_true", help="Refresh from source first.")

    p_build = sub.add_parser(
        "build",
        help="Pipeline: fetch the IMD workbook, parse, validate, and write data/ (CI).",
    )
    p_build.add_argument("--data-dir", default=None, help="Output directory (default: ./data).")
    p_build.add_argument("--force", action="store_true", help="Rebuild even if unchanged.")

    p_ib = sub.add_parser(
        "build-ibtracs",
        help="Pipeline: fetch IBTrACS (North Indian Ocean), write data/ibtracs/ (CI).",
    )
    p_ib.add_argument("--data-dir", default=None, help="Output directory (default: ./data).")
    p_ib.add_argument("--force", action="store_true", help="Rebuild even if unchanged.")

    p_cmp = sub.add_parser("compare", help="Compare the IMD record with IBTrACS, storm by storm.")
    p_cmp.add_argument("--out", default=None, help="Write per-fix differences to this CSV.")
    p_cmp.add_argument("--ib-wind", choices=["usa", "wmo", "imd", "merged"], default="usa")
    p_cmp.add_argument(
        "--wind-scale", type=float, default=1.0, help="Multiply IBTrACS wind by this."
    )

    p_act = sub.add_parser("active", help="List currently active storms from an ATCF server.")
    p_act.add_argument("--source", choices=["nhc", "jtwc"], default="jtwc")
    p_act.add_argument(
        "--basin", action="append", help="ATCF basin code (io, sh, wp, al, ep); repeatable."
    )
    p_act.add_argument("--max-age-hours", type=float, default=12.0)

    args = p.parse_args(argv)

    if args.cmd == "active":
        from .realtime import active_storms

        bt = active_storms(args.source, basins=args.basin, max_age_hours=args.max_age_hours)
        if bt.storms.empty:
            print("No active storms.")
        else:
            cols = ["storm_id", "name", "basin", "end_time", "max_wind", "min_pressure"]
            print(bt.storms[cols].to_string(index=False))
        return 0

    if args.cmd == "build-ibtracs":
        from pathlib import Path

        from . import _repo
        from .ibtracs import build_ibtracs

        try:
            changed, m = build_ibtracs(Path(args.data_dir or _repo.DATA_DIR_NAME), force=args.force)
        except Exception as exc:  # fail loudly; published data stays untouched
            print(f"::error::IBTrACS pipeline failed: {exc}", file=sys.stderr)
            return 1
        verb = "UPDATED" if changed else "NO CHANGE"
        print(
            f"{verb}: IBTrACS {m.basin} {m.n_storms} storms, {m.n_obs} fixes, "
            f"{m.year_min}-{m.year_max}, sha256={m.source_sha256[:12]}"
        )
        return 0

    if args.cmd == "compare":
        from .compare import compare_tracks
        from .ibtracs import load_ibtracs

        res = compare_tracks(
            load(), load_ibtracs(), ib_wind=args.ib_wind, ib_wind_scale=args.wind_scale
        )
        print(repr(res))
        print(res.summary().round(2).to_string())
        if args.out:
            res.fixes.to_csv(args.out, index=False)
            print(f"Wrote {len(res.fixes)} common fixes to {args.out}")
        return 0

    if args.cmd == "build":
        from pathlib import Path

        from . import _repo
        from .pipeline import main as build_main

        data_dir = args.data_dir or _repo.DATA_DIR_NAME
        return build_main(["--data-dir", str(Path(data_dir))] + (["--force"] if args.force else []))

    if args.cmd == "update":
        bt = load(update=True, source=args.source, force=args.force)
        print(f"Updated: {bt!r}")
    elif args.cmd == "info":
        bt = load(source=args.source)
        print(repr(bt))
        if not bt.storms.empty:
            print(
                bt.storms[
                    [
                        "storm_id",
                        "name",
                        "basin",
                        "start_time",
                        "peak_grade",
                        "max_wind",
                        "min_pressure",
                    ]
                ]
                .tail(10)
                .to_string(index=False)
            )
    elif args.cmd == "export":
        bt = load(source=args.source, update=args.update)
        if args.out.endswith(".parquet"):
            bt.observations.to_parquet(args.out, index=False)
        else:
            bt.observations.to_csv(args.out, index=False)
        print(f"Wrote {len(bt.observations)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
