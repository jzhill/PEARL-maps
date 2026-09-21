"""Stage 04 - render village orientation sheets.

Renders every `village` job in data/processed/plan.csv to

    outputs/village_maps/<village>_orientation_map_<yymmdd>.pdf

and appends a row per sheet to outputs/village_maps/_build_log.csv.

Run:  uv run python scripts/04_render_village_maps.py [--only Bikenibeu] [--date 260920]
"""
import argparse
import csv
import sys
import time

from pearl_maps.config import date_stamp, load_config, village_slug
from pearl_maps.data import load_processed
from pearl_maps.plan import read_plan
from pearl_maps.village_map import VILLAGE_LOG_FIELDS, VillageMapRenderer


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 04 - render village orientation sheets")
    ap.add_argument("--config")
    ap.add_argument("--only", action="append", help="render only these villages")
    ap.add_argument("--date", help="yymmdd stamp for file names (default: today)")
    ap.add_argument("--style", choices=["bw", "osm"])
    args = ap.parse_args()
    cfg = load_config(args.config)
    ds = load_processed(cfg)
    jobs = [j for j in read_plan(cfg.paths.plan) if j.kind == "village"]
    if args.only:
        jobs = [j for j in jobs if j.village in set(args.only)]
    if not jobs:
        print("no village jobs in plan")
        return 0

    stamp = args.date or date_stamp()
    out_dir = cfg.paths.village_maps
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = VillageMapRenderer(cfg, ds, style=args.style)
    log = out_dir / "_build_log.csv"
    t0 = time.time()
    for n, job in enumerate(jobs, 1):
        pdf = out_dir / f"{village_slug(job.village)}_orientation_map_{stamp}.pdf"
        r = renderer.render(job.village, pdf)
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["date"] + VILLAGE_LOG_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"date": stamp, **r.row()})
        print(f"[{n}/{len(jobs)}] {job.village}: {r.panels} panel(s), 1:{r.scale:,}, "
              f"{r.ea_labels} EA labels, {r.landmarks} landmarks  "
              f"({time.time() - t0:.0f}s)", flush=True)
    print(f"done -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
