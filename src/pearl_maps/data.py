"""Raw-input loading, cleaning, and the processed datasets the renderers use.

Stage 01 (prepare) calls the ``read_raw_*`` functions, cleans, and writes
``data/processed``. Every later stage calls :func:`load_processed` and never
touches the raw CSV / GeoJSON again. The OSM GeoPackage is read in place from
``data/raw`` because it is already spatially indexed.
"""
from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from .config import Config
from .gpkg import GeoPackage
from .landmarks import CATEGORIES, CONFIDENCE_LEVELS, Landmark

# An EA whose bounding box spans more than this (degrees, ~11 km) is treated
# as corrupt. South Tarawa EAs are a few hundred metres across.
MAX_EA_SPAN_DEG = 0.1


# ---------------------------------------------------------------- records

@dataclass(slots=True)
class EA:
    id: str
    village: str
    island: str
    geom: BaseGeometry
    geometry_ok: bool = True


@dataclass(slots=True)
class Household:
    idx: int                 # row number, stable within one processed file
    key: str                 # interview__key from the listing
    ea: str
    village: str
    head_name: str           # as listed
    label: str | None        # cleaned for printing; None = marker only
    lon: float
    lat: float
    occupancy: str
    dwelling_type: str
    in_scope: bool           # plotted at all (occupied private household)
    inside_own_ea: bool | None = None


@dataclass
class Datasets:
    eas: dict[str, EA]               # geometry_ok EAs only
    households: list[Household]      # all listed households; filter on in_scope
    osm: GeoPackage
    landmarks: list[Landmark] = field(default_factory=list)   # printable ones, best first

    def households_in(self, ea_ids) -> list[Household]:
        s = set(ea_ids)
        return [h for h in self.households if h.in_scope and h.ea in s]

    def village_eas(self, village: str) -> list[str]:
        return sorted(e for e, v in self.eas.items() if v.village == village)


# ---------------------------------------------------------------- names

_PLACEHOLDER = re.compile(r"##|^\s*(\.a|n/?a|na|none|-)\s*$", re.IGNORECASE)


def clean_head_name(raw: str | None, max_chars: int = 30) -> str | None:
    """Printable household-head label, or None when there is no usable name.

    - placeholders such as ``##N/A##`` and ``.a`` -> None (marker is still drawn)
    - trailing notes in brackets are dropped
    - ``Head.Two`` -> ``Head. Two``; whitespace collapsed
    - longer than ``max_chars`` -> truncated with an ellipsis
    """
    s = (raw or "").strip()
    if not s or _PLACEHOLDER.search(s):
        return None
    s = re.sub(r"\s*\(.*$", "", s)
    s = re.sub(r"\s*\.\s*", ". ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if not s:
        return None
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


# ---------------------------------------------------------------- raw inputs

def _in_scope_ea(props: dict, scope: dict) -> bool:
    if props.get("iid_name") in scope.get("islands", []):
        return True
    for ev in scope.get("extra_villages", []) or []:
        if props.get("iid_name") == ev["island"] and props.get("vid_name") == ev["village"]:
            return True
    return False


def read_raw_eas(path: Path, scope: dict) -> dict[str, EA]:
    with open(path, encoding="utf-8") as fh:
        gj = json.load(fh)
    out: dict[str, EA] = {}
    for f in gj["features"]:
        p = f["properties"]
        if p.get("ea_2020") is None or not _in_scope_ea(p, scope):
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        minx, miny, maxx, maxy = g.bounds
        ok = (maxx - minx) < MAX_EA_SPAN_DEG and (maxy - miny) < MAX_EA_SPAN_DEG
        ea_id = str(int(p["ea_2020"]))
        out[ea_id] = EA(ea_id, p.get("vid_name") or "", p.get("iid_name") or "", g, ok)
    return out


def read_raw_households(path: Path, hh_cfg: dict) -> list[Household]:
    occ_ok = set(hh_cfg["occupancy"])
    dwell_ok = set(hh_cfg["dwelling_type"])
    max_chars = int(hh_cfg["max_label_chars"])
    rows: list[Household] = []
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if not r.get("x_final") or not r.get("y_final"):
                continue
            rows.append(Household(
                idx=len(rows),
                key=r.get("interview__key", ""),
                ea=r["eaid_corr"].strip(),
                village=r.get("vid_name", ""),
                head_name=(r.get("head_string") or "").strip(),
                label=clean_head_name(r.get("head_string"), max_chars),
                lon=float(r["x_final"]),
                lat=float(r["y_final"]),
                occupancy=r.get("occupancy", ""),
                dwelling_type=r.get("dwell_type", ""),
                in_scope=(r.get("occupancy") in occ_ok and r.get("dwell_type") in dwell_ok),
            ))
    return rows


LANDMARK_REQUIRED = ("landmark_id", "name", "category", "lon", "lat", "confidence")


def read_raw_landmarks(path: Path) -> list[dict]:
    """Rows of landmarks.csv as dicts, validated. Raises ValueError listing every bad row.

    The file is edited by hand, so a typo in `category` or `confidence` must stop
    stage 01 rather than silently drop a landmark from the maps.
    """
    rows: list[dict] = []
    problems: list[str] = []
    with open(path, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in LANDMARK_REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: missing column(s) {missing}")
        seen: set[str] = set()
        for n, r in enumerate(reader, start=2):          # line 1 is the header
            where = f"{path.name} line {n} ({r.get('name', '')!r})"
            try:
                r["lon"], r["lat"] = float(r["lon"]), float(r["lat"])
            except ValueError:
                problems.append(f"{where}: lon/lat is not a number")
                continue
            if not (172.0 <= r["lon"] <= 174.0 and 0.5 <= r["lat"] <= 2.5):
                problems.append(f"{where}: lon/lat {r['lon']}, {r['lat']} is not near Tarawa "
                                "(are they swapped?)")
            if r["category"] not in CATEGORIES:
                problems.append(f"{where}: category {r['category']!r} is not one of {list(CATEGORIES)}")
            if r["confidence"] not in CONFIDENCE_LEVELS:
                problems.append(f"{where}: confidence {r['confidence']!r} is not one of "
                                f"{list(CONFIDENCE_LEVELS)}")
            if not (r.get("label") or r["name"]).strip():
                problems.append(f"{where}: no name or label")
            if r["landmark_id"] in seen:
                problems.append(f"{where}: duplicate landmark_id {r['landmark_id']}")
            seen.add(r["landmark_id"])
            rows.append(r)
    if problems:
        raise ValueError("landmarks file has problems:\n  " + "\n  ".join(problems))
    return rows


SNAP_INLAND_M = 6.0      # a landmark moved onto land is put this far in from the shoreline


def _metres(a: Point, b: Point) -> float:
    return math.hypot((a.x - b.x) * 111320 * math.cos(math.radians(a.y)), (a.y - b.y) * 110574)


def snap_to_land(rows: list[dict], osm, max_snap_m: float) -> list[tuple[dict, float | None]]:
    """Move landmarks that lie in the lagoon or ocean onto the nearest land.

    Edits ``rows`` in place (lon/lat, and a note saying so). Returns
    ``(row, metres_moved)`` for each landmark that was off land; ``None`` means it
    is further than ``max_snap_m`` from any land and was left alone for a human to look at.
    """
    if not rows:
        return []
    lons, lats = [r["lon"] for r in rows], [r["lat"] for r in rows]
    pad = 0.01
    land = unary_union([g for g, _ in osm.query(
        "land", (min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad))])
    if land.is_empty:
        return []
    inland = land.buffer(-SNAP_INLAND_M / 111000.0)
    out: list[tuple[dict, float | None]] = []
    for r in rows:
        p = Point(r["lon"], r["lat"])
        if land.covers(p):
            continue
        q = nearest_points(land, p)[0]
        d = _metres(p, q)
        if d > max_snap_m:
            out.append((r, None))
            continue
        if not inland.is_empty:
            s = nearest_points(inland, p)[0]
            if _metres(p, s) <= d + 3 * SNAP_INLAND_M:      # the shrunk land still holds this shore
                q = s
        r["lon"], r["lat"] = q.x, q.y
        r["notes"] = "; ".join(x for x in (r.get("notes", ""),
                                           f"moved {d:.0f} m onto land by stage 01 (source point was in the water)") if x)
        out.append((r, d))
    return out


def flag_inside_own_ea(households: list[Household], eas: dict[str, EA]) -> None:
    from shapely.prepared import prep
    prepared = {e: prep(v.geom.buffer(1e-6)) for e, v in eas.items() if v.geometry_ok}
    for h in households:
        pg = prepared.get(h.ea)
        h.inside_own_ea = None if pg is None else pg.contains(Point(h.lon, h.lat))


# ---------------------------------------------------------------- processed

HH_FIELDS = ["idx", "hh_key", "ea_id", "village", "head_name", "label", "lon", "lat",
             "occupancy", "dwelling_type", "in_scope", "inside_own_ea"]


def write_processed(cfg: Config, eas: dict[str, EA], households: list[Household]) -> None:
    cfg.paths.processed.mkdir(parents=True, exist_ok=True)
    features = [{
        "type": "Feature",
        "properties": {"ea_id": e.id, "village": e.village, "island": e.island,
                       "geometry_ok": e.geometry_ok},
        "geometry": mapping(e.geom),
    } for e in sorted(eas.values(), key=lambda x: x.id)]
    with open(cfg.paths.eas, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)

    with open(cfg.paths.households, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HH_FIELDS)
        for h in households:
            w.writerow([h.idx, h.key, h.ea, h.village, h.head_name, h.label or "",
                        f"{h.lon:.8f}", f"{h.lat:.8f}", h.occupancy, h.dwelling_type,
                        int(h.in_scope),
                        "" if h.inside_own_ea is None else int(h.inside_own_ea)])


LANDMARK_PROPS = ("landmark_id", "name", "label", "alt_name", "category", "subtype", "village",
                  "confidence", "code", "source", "notes")


def write_landmarks(cfg: Config, rows: list[dict]) -> None:
    """data/processed/landmarks.geojson: every row of landmarks.csv (filtering happens at load)."""
    cfg.paths.processed.mkdir(parents=True, exist_ok=True)
    features = [{
        "type": "Feature",
        "properties": {k: (r.get(k) or "") for k in LANDMARK_PROPS},
        "geometry": mapping(Point(r["lon"], r["lat"])),
    } for r in rows]
    with open(cfg.paths.landmarks, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, ensure_ascii=False)


def load_landmarks(cfg: Config) -> list[Landmark]:
    """Printable landmarks, best first: config priority, then confidence, then label."""
    with open(cfg.paths.landmarks, encoding="utf-8") as fh:
        gj = json.load(fh)
    floor = CONFIDENCE_LEVELS.index(cfg.landmarks["min_confidence"])
    prio = cfg.landmarks["priority"]
    out = []
    for f in gj["features"]:
        p = f["properties"]
        if CONFIDENCE_LEVELS.index(p["confidence"]) < floor:
            continue
        out.append(Landmark(name=(p["label"] or p["name"]).strip(), category=p["category"],
                            point=shape(f["geometry"]), priority=int(prio.get(p["category"], 9)),
                            confidence=p["confidence"]))
    out.sort(key=lambda lm: (lm.priority, -CONFIDENCE_LEVELS.index(lm.confidence), lm.name.lower()))
    return out


def load_processed(cfg: Config) -> Datasets:
    for p in (cfg.paths.eas, cfg.paths.households, cfg.paths.landmarks):
        if not p.exists():
            raise FileNotFoundError(f"{p} not found - run scripts/01_prepare.py first")
    with open(cfg.paths.eas, encoding="utf-8") as fh:
        gj = json.load(fh)
    eas = {}
    for f in gj["features"]:
        p = f["properties"]
        if not p["geometry_ok"]:
            continue
        eas[p["ea_id"]] = EA(p["ea_id"], p["village"], p["island"], shape(f["geometry"]))

    households = []
    with open(cfg.paths.households, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            households.append(Household(
                idx=int(r["idx"]), key=r["hh_key"], ea=r["ea_id"], village=r["village"],
                head_name=r["head_name"], label=r["label"] or None,
                lon=float(r["lon"]), lat=float(r["lat"]),
                occupancy=r["occupancy"], dwelling_type=r["dwelling_type"],
                in_scope=r["in_scope"] == "1",
                inside_own_ea=None if r["inside_own_ea"] == "" else r["inside_own_ea"] == "1",
            ))
    osm = GeoPackage(cfg.paths.raw_input(cfg, "osm"))
    return Datasets(eas, households, osm, load_landmarks(cfg))
