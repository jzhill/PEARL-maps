"""Stage 01 - prepare.

Reads the three raw inputs from data/raw/, keeps the EAs in scope, cleans
household-head names, flags data problems, and writes:

    data/processed/eas.geojson      EAs in scope, with village and a geometry_ok flag
    data/processed/households.csv   every listed household, cleaned label, in_scope flag
    data/processed/qa_report.md     data-quality summary (read this after each new extract)
    data/processed/qa_issues.csv    one row per flagged EA / household

Run:  uv run python scripts/01_prepare.py
"""
import argparse
import sys

from pearl_maps.config import load_config
from pearl_maps.data import (flag_inside_own_ea, read_raw_eas, read_raw_households,
                             write_processed)
from pearl_maps.gpkg import GeoPackage
from pearl_maps.qa import run_checks, write_report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", help="path to config.yaml (default: repo root)")
    args = ap.parse_args()
    cfg = load_config(args.config)

    missing = [k for k in ("ea_boundaries", "households", "osm")
               if not cfg.paths.raw_input(cfg, k).exists()]
    if missing:
        for k in missing:
            print(f"missing raw input: {cfg.paths.raw_input(cfg, k)}")
        print("Copy the files into data/raw/ (see data/raw/README.md) or fix "
              "`inputs:` in config.yaml.")
        return 1

    print("reading EA boundaries ...")
    eas = read_raw_eas(cfg.paths.raw_input(cfg, "ea_boundaries"), cfg.scope)
    print(f"  {len(eas)} EAs in scope, {sum(not e.geometry_ok for e in eas.values())} "
          "with bad geometry")

    print("reading household listing ...")
    hh = read_raw_households(cfg.paths.raw_input(cfg, "households"), cfg.households)
    print(f"  {len(hh)} households, {sum(h.in_scope for h in hh)} occupied private")

    print("checking OSM GeoPackage ...")
    layers = GeoPackage(cfg.paths.raw_input(cfg, "osm")).layers()
    needed = {"land", "natural", "landuse", "buildings", "highway_ln", "amenity", "shop"}
    if needed - set(layers):
        print(f"  OSM GeoPackage is missing layers: {sorted(needed - set(layers))}")
        return 1
    print(f"  {len(layers)} layers ok")

    flag_inside_own_ea(hh, eas)
    write_processed(cfg, eas, hh)
    issues = run_checks(eas, hh)
    write_report(cfg, eas, hh, issues)
    print(f"wrote {cfg.paths.eas.name}, {cfg.paths.households.name}, "
          f"{cfg.paths.qa_report.name} ({len(issues)} issues) to {cfg.paths.processed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
