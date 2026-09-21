"""Stage 03 - render EA maps.

Renders every `ea` job in data/processed/plan.csv to

    outputs/ea_maps/<village>/<ea_id>_enumeration_map_<yymmdd>.pdf
    outputs/ea_maps/<village>/<ea_id>_enumeration_map_<yymmdd>{a,b,..}.pdf   (split EAs)

and appends one row per page to outputs/ea_maps/<village>/_build_log.csv.
A page with complete=0 did not fit every name and needs attention.

Run:  uv run python scripts/03_render_ea_maps.py [--only 70502220] [--date 260920]
"""
import argparse
import csv
import sys
import time

from pearl_maps.config import date_stamp, load_config, village_slug
from pearl_maps.data import load_processed
from pearl_maps.ea_map import LOG_FIELDS, EAMapRenderer
from pearl_maps.plan import read_plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 03 - render EA maps")
    ap.add_argument("--config")
    ap.add_argument("--only", action="append", help="render only these job ids")
    ap.add_argument("--date", help="yymmdd stamp for file names (default: today)")
    ap.add_argument("--style", choices=["bw", "osm"], help="override ea_map.style")
    ap.add_argument("--verbose", action="store_true", help="print each font-size attempt")
    args = ap.parse_args()
    cfg = load_config(args.config)
    ds = load_processed(cfg)
    jobs = [j for j in read_plan(cfg.paths.plan) if j.kind == "ea"]
    if args.only:
        jobs = [j for j in jobs if j.job in set(args.only)]
    if not jobs:
        print("no EA jobs in plan")
        return 0

    stamp = args.date or date_stamp()
    renderer = EAMapRenderer(cfg, ds, style=args.style, verbose=args.verbose)
    t0, incomplete = time.time(), []
    for n, job in enumerate(jobs, 1):
        out_dir = cfg.paths.ea_maps / village_slug(job.village)
        pages = renderer.render(job.ea_ids, out_dir,
                                f"{'-'.join(job.ea_ids)}_enumeration_map_{stamp}")
        log = out_dir / "_build_log.csv"
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["date"] + LOG_FIELDS)
            if new:
                w.writeheader()
            for p in pages:
                w.writerow({"date": stamp, **p.row()})
        ok = all(p.complete for p in pages)
        if not ok:
            incomplete.append(job.job)
        print(f"[{n}/{len(jobs)}] {job.job} {job.village}: {len(pages)} page(s), "
              f"{min(p.font_pt for p in pages):g}pt, "
              f"{'ok' if ok else 'INCOMPLETE'}  ({time.time() - t0:.0f}s)", flush=True)

    print(f"done: {len(jobs)} EAs in {time.time() - t0:.0f}s -> {cfg.paths.ea_maps}")
    if incomplete:
        print(f"incomplete (names missing): {', '.join(incomplete)}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
