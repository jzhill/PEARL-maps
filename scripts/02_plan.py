"""Stage 02 - plan.

Decides what to render and writes data/processed/plan.csv: one row per EA
map job and one per village orientation sheet. By default every EA marked
`pending` in config/ea_status.csv is planned.

Examples:
    uv run python scripts/02_plan.py                          # all pending EAs
    uv run python scripts/02_plan.py --village Temaiku        # pending EAs in one village
    uv run python scripts/02_plan.py --village Bikenibeu --include-mapped   # redo a village
    uv run python scripts/02_plan.py --ea 70502220 --ea 70502230            # specific EAs
    uv run python scripts/02_plan.py --village Eita --village-sheets-only   # orientation sheet only
"""
import argparse
import sys
from collections import Counter

from pearl_maps.config import load_config
from pearl_maps.data import load_processed
from pearl_maps.plan import build_plan, read_status, write_plan


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 02 - plan")
    ap.add_argument("--config")
    ap.add_argument("--village", action="append", help="limit to a village (repeatable)")
    ap.add_argument("--ea", action="append", help="specific EA id (repeatable)")
    ap.add_argument("--include-mapped", action="store_true",
                    help="also plan EAs already marked mapped")
    ap.add_argument("--no-village-sheets", action="store_true",
                    help="plan EA maps only")
    ap.add_argument("--village-sheets-only", action="store_true",
                    help="plan orientation sheets only (needs --village)")
    args = ap.parse_args()
    cfg = load_config(args.config)
    ds = load_processed(cfg)
    status = read_status(cfg.paths.status)

    jobs, warnings = build_plan(ds, status, villages=args.village, ea_ids=args.ea,
                                include_mapped=args.include_mapped,
                                village_sheets=not args.no_village_sheets)
    if args.village_sheets_only:
        jobs = [j for j in jobs if j.kind == "village"]
    for w in warnings:
        print(f"warning: {w}")
    write_plan(cfg.paths.plan, jobs)

    ea_jobs = [j for j in jobs if j.kind == "ea"]
    print(f"planned {len(ea_jobs)} EA maps "
          f"({sum(j.households for j in ea_jobs)} households) and "
          f"{sum(j.kind == 'village' for j in jobs)} village sheets -> {cfg.paths.plan}")
    for v, n in sorted(Counter(j.village for j in ea_jobs).items()):
        print(f"  {v:18} {n:3} EAs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
