"""Data-quality checks run by stage 01. Nothing here changes the data; it
reports what the renderers will do about each problem."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime

from .config import Config
from .data import EA, Household

ISSUE_FIELDS = ["check", "ea_id", "village", "hh_key", "detail"]

EXPLAIN = {
    "ea_bad_geometry": "EA polygon is corrupt (spans > ~11 km); EA is excluded from all maps.",
    "ea_no_households": "EA has no occupied private households in the listing.",
    "hh_unknown_ea": "Household's EA id is not in the EA boundary file; not mapped.",
    "hh_no_name": "No usable head name (e.g. ##N/A##); drawn as a marker with no label.",
    "hh_outside_own_ea": "Household point falls outside its own EA polygon; still mapped with that EA.",
}


def run_checks(eas_all: dict[str, EA], households: list[Household]) -> list[dict]:
    issues: list[dict] = []
    good = {e for e, v in eas_all.items() if v.geometry_ok}
    for e, v in sorted(eas_all.items()):
        if not v.geometry_ok:
            b = v.geom.bounds
            issues.append(dict(check="ea_bad_geometry", ea_id=e, village=v.village, hh_key="",
                               detail=f"bounds {b[0]:.3f},{b[1]:.3f} to {b[2]:.3f},{b[3]:.3f}"))
    counts = Counter(h.ea for h in households if h.in_scope)
    for e in sorted(good):
        if counts[e] == 0:
            issues.append(dict(check="ea_no_households", ea_id=e, village=eas_all[e].village,
                               hh_key="", detail=""))
    for h in households:
        if not h.in_scope:
            continue
        if h.ea not in eas_all:
            issues.append(dict(check="hh_unknown_ea", ea_id=h.ea, village=h.village,
                               hh_key=h.key, detail=h.head_name))
            continue
        if h.label is None:
            issues.append(dict(check="hh_no_name", ea_id=h.ea, village=h.village,
                               hh_key=h.key, detail=h.head_name))
        if h.inside_own_ea is False:
            issues.append(dict(check="hh_outside_own_ea", ea_id=h.ea, village=h.village,
                               hh_key=h.key, detail=h.head_name))
    return issues


def write_report(cfg: Config, eas_all: dict[str, EA], households: list[Household],
                 issues: list[dict]) -> None:
    with open(cfg.paths.qa_issues, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ISSUE_FIELDS)
        w.writeheader()
        w.writerows(issues)

    in_scope = [h for h in households if h.in_scope]
    by_check = Counter(i["check"] for i in issues)
    by_village = Counter((i["village"], i["check"]) for i in issues)
    villages = sorted({v.village for v in eas_all.values()})
    lines = [
        "# PEARL-maps data-quality report",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `scripts/01_prepare.py`.",
        "",
        "## Inputs",
        "",
        f"- EA boundaries: `{cfg.inputs['ea_boundaries']}` - {len(eas_all)} EAs in scope",
        f"- Households: `{cfg.inputs['households']}` - {len(households)} records, "
        f"{len(in_scope)} occupied private households mapped",
        f"- Basemap: `{cfg.inputs['osm']}`",
        "",
        "## Issues",
        "",
        "| check | count | what the maps do |",
        "|---|---:|---|",
    ]
    for chk, text in EXPLAIN.items():
        lines.append(f"| `{chk}` | {by_check.get(chk, 0)} | {text} |")
    lines += ["", "## By village", "",
              "| village | EAs | households | " + " | ".join(f"`{c}`" for c in EXPLAIN) + " |",
              "|---|---:|---:|" + "---:|" * len(EXPLAIN)]
    ea_by_v = Counter(v.village for v in eas_all.values())
    hh_by_v = Counter(eas_all[h.ea].village for h in in_scope if h.ea in eas_all)
    for v in villages:
        cells = " | ".join(str(by_village.get((v, c), 0)) for c in EXPLAIN)
        lines.append(f"| {v} | {ea_by_v[v]} | {hh_by_v[v]} | {cells} |")
    lines += ["", f"Row-level detail: `{cfg.paths.qa_issues.name}`.", ""]
    cfg.paths.qa_report.write_text("\n".join(lines), encoding="utf-8")
