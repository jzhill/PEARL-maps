"""Utility - update config/ea_status.csv from map files you have delivered.

Maps are copied to the field folders by hand, so this scans a folder (for
example a shared field-map folder) for files named like
`70502220_enumeration_map_260920.pdf` and marks those EAs `mapped`. It never
downgrades a status and never touches EAs marked `blocked`. It also adds any
in-scope EA missing from the register as `pending`.

Run:
    uv run python scripts/sync_status.py --maps-dir "<folder of delivered maps>"
    uv run python scripts/sync_status.py --maps-dir ... --dry-run
"""
import argparse
import sys
from pathlib import Path

from pearl_maps.config import load_config
from pearl_maps.data import load_processed
from pearl_maps.plan import StatusRow, read_status, sync_status_from_maps, write_status


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync EA status from delivered map files")
    ap.add_argument("--config")
    ap.add_argument("--maps-dir", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = load_config(args.config)
    ds = load_processed(cfg)
    status = read_status(cfg.paths.status) if cfg.paths.status.exists() else {}

    added = []
    for e, v in ds.eas.items():
        if e not in status:
            status[e] = StatusRow(e, v.village, "pending")
            added.append(e)
    files = [p.name for p in args.maps_dir.rglob("*.pdf")]
    changes = sync_status_from_maps(status, files, {e: v.village for e, v in ds.eas.items()})

    for e in added:
        print(f"{e}: added as pending")
    for c in changes:
        print(c)
    if not (added or changes):
        print("status register already up to date")
    elif args.dry_run:
        print("(dry run - nothing written)")
    else:
        write_status(cfg.paths.status, status)
        print(f"wrote {cfg.paths.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
