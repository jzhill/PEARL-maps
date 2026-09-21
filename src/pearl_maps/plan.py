"""The EA status register and the render plan.

``config/ea_status.csv`` is the tracked record of which EAs already have
maps. It is edited by hand once maps are checked and sent to the field:

    ea_id,village,status,map_date,note
    70502220,Bikenibeu,mapped,2026-09-20,
    61401401,Buota,blocked,,no households in PEARL listing (Aug 2025 extract)

status is one of ``pending`` | ``mapped`` | ``blocked``. ``scripts/sync_status.py``
marks EAs mapped from the map files you have delivered.

``02_plan`` turns the register plus command-line filters into
``data/processed/plan.csv``: one row per EA page job and one per village sheet.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .data import Datasets

STATUS_FIELDS = ["ea_id", "village", "status", "map_date", "note"]
STATUSES = {"pending", "mapped", "blocked"}
PLAN_FIELDS = ["job", "kind", "village", "ea_ids", "households", "status"]


@dataclass
class StatusRow:
    ea_id: str
    village: str
    status: str
    map_date: str = ""
    note: str = ""


def read_status(path: Path) -> dict[str, StatusRow]:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            st = r["status"].strip().lower()
            if st not in STATUSES:
                raise ValueError(f"{path}: EA {r['ea_id']} has unknown status {st!r}")
            out[r["ea_id"].strip()] = StatusRow(r["ea_id"].strip(), r["village"].strip(), st,
                                                r.get("map_date", "").strip(),
                                                r.get("note", "").strip())
    return out


def write_status(path: Path, rows: dict[str, StatusRow]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(STATUS_FIELDS)
        for r in sorted(rows.values(), key=lambda r: (r.village, r.ea_id)):
            w.writerow([r.ea_id, r.village, r.status, r.map_date, r.note])


@dataclass
class Job:
    job: str
    kind: str            # "ea" | "village"
    village: str
    ea_ids: list[str]
    households: int
    status: str

    def row(self) -> dict:
        return dict(job=self.job, kind=self.kind, village=self.village,
                    ea_ids=";".join(self.ea_ids), households=self.households,
                    status=self.status)


def build_plan(ds: Datasets, status: dict[str, StatusRow], villages: list[str] | None = None,
               ea_ids: list[str] | None = None, include_mapped: bool = False,
               village_sheets: bool = True) -> tuple[list[Job], list[str]]:
    """Jobs to render, and warnings. With no filters: every pending EA."""
    warnings: list[str] = []
    wanted: list[str] = []
    if ea_ids:
        for e in ea_ids:
            if e not in ds.eas:
                warnings.append(f"EA {e}: not a mappable EA (unknown or bad geometry) - skipped")
            else:
                wanted.append(e)
    else:
        for e, v in sorted(ds.eas.items()):
            if villages and v.village not in villages:
                continue
            st = status.get(e)
            if st is None:
                warnings.append(f"EA {e} ({v.village}) is not in the status register - "
                                "treated as pending")
                wanted.append(e)
            elif st.status == "pending" or (include_mapped and st.status == "mapped"):
                wanted.append(e)
    if villages:
        known = {v.village for v in ds.eas.values()}
        for v in villages:
            if v not in known:
                warnings.append(f"village {v!r}: no mappable EAs (check spelling, e.g. "
                                f"'Betio_East')")

    counts: dict[str, int] = {}
    for h in ds.households:
        if h.in_scope:
            counts[h.ea] = counts.get(h.ea, 0) + 1
    jobs = []
    for e in wanted:
        if counts.get(e, 0) == 0:
            warnings.append(f"EA {e}: no occupied private households - skipped")
            continue
        st = status.get(e)
        jobs.append(Job(e, "ea", ds.eas[e].village, [e], counts[e],
                        st.status if st else "pending"))
    if village_sheets:
        for v in sorted({j.village for j in jobs} | set(villages or [])):
            if ds.village_eas(v):
                n = sum(counts.get(e, 0) for e in ds.village_eas(v))
                jobs.append(Job(v, "village", v, ds.village_eas(v), n, ""))
    return jobs, warnings


def write_plan(path: Path, jobs: list[Job]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=PLAN_FIELDS)
        w.writeheader()
        for j in jobs:
            w.writerow(j.row())


def read_plan(path: Path) -> list[Job]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run scripts/02_plan.py first")
    with open(path, encoding="utf-8") as fh:
        return [Job(r["job"], r["kind"], r["village"], r["ea_ids"].split(";"),
                    int(r["households"]), r["status"]) for r in csv.DictReader(fh)]


# ---------------------------------------------------------------- sync from files

_MAP_NAME = re.compile(r"^(?P<ids>\d{8}[a-h]?(?:-\d{2,8}[a-h]?)*)_.*?map_(?P<date>\d{6})",
                        re.IGNORECASE)


def parse_map_filename(name: str) -> tuple[list[str], str] | None:
    """EA ids and yymmdd date from an existing map file name.

    ``71506320-6310a_ea_map_250915.pdf`` -> (["71506320", "71506310"], "250915")
    Short trailing ids borrow the leading digits of the first id.
    """
    m = _MAP_NAME.match(name)
    if not m:
        return None
    parts = [re.sub(r"[a-h]$", "", p, flags=re.IGNORECASE) for p in m["ids"].split("-")]
    base = parts[0]
    ids = [base] + [base[: 8 - len(p)] + p for p in parts[1:]]
    return ids, m["date"]


def sync_status_from_maps(status: dict[str, StatusRow], files: list[str],
                          ds_villages: dict[str, str]) -> list[str]:
    """Mark EAs ``mapped`` when a map file exists for them. Never downgrades a
    status, never touches ``blocked``. Returns a list of changes."""
    changes = []
    latest: dict[str, str] = {}
    for f in files:
        parsed = parse_map_filename(f)
        if not parsed:
            continue
        ids, d = parsed
        for e in ids:
            latest[e] = max(latest.get(e, ""), d)
    for e, d in sorted(latest.items()):
        iso = f"20{d[:2]}-{d[2:4]}-{d[4:]}"
        row = status.get(e)
        if row is None:
            if e not in ds_villages:
                changes.append(f"{e}: map file found but EA is not in scope - ignored")
                continue
            status[e] = StatusRow(e, ds_villages[e], "mapped", iso, "")
            changes.append(f"{e}: added as mapped ({iso})")
        elif row.status == "pending":
            row.status, row.map_date = "mapped", iso
            changes.append(f"{e}: pending -> mapped ({iso})")
        elif row.status == "mapped" and iso > row.map_date:
            row.map_date = iso
            changes.append(f"{e}: map date -> {iso}")
    return changes
