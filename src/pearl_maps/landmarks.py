"""Named orientation features from the OSM GeoPackage, best first."""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point

from .style import (LANDMARK_AMENITY, LANDMARK_JUNK, LANDMARK_NAME_WORDS,
                    LANDMARK_PRIORITY, LANDMARK_SHOPS)


@dataclass(frozen=True)
class Landmark:
    name: str
    category: str      # school | health | church | gov | shop | named
    point: Point       # lon/lat

    @property
    def priority(self) -> int:
        return LANDMARK_PRIORITY.get(self.category, 5)


def collect_landmarks(osm, bbox, max_name_len: int = 42) -> list[Landmark]:
    found: list[Landmark] = []
    for g, a in osm.query("amenity", bbox, ("amenity", "name")):
        cat = LANDMARK_AMENITY.get(a["amenity"])
        if cat and a["name"]:
            found.append(Landmark(a["name"].strip(), cat, g.centroid))
    for g, a in osm.query("shop", bbox, ("shop", "name")):
        if a["name"] and a["shop"] in LANDMARK_SHOPS:
            found.append(Landmark(a["name"].strip(), "shop", g.centroid))
    for g, a in osm.query("buildings", bbox, ("name", "amenity")):
        if not a["name"]:
            continue
        name = a["name"].strip()
        cat = LANDMARK_AMENITY.get(a["amenity"] or "")
        if cat is None:
            if not any(w in name.lower() for w in LANDMARK_NAME_WORDS):
                continue
            cat = "named"
        found.append(Landmark(name, cat, g.centroid))

    seen: set[str] = set()
    out: list[Landmark] = []
    for lm in sorted(found, key=lambda l: l.priority):
        k = lm.name.lower()
        if k in seen or k in LANDMARK_JUNK or len(lm.name) > max_name_len:
            continue
        seen.add(k)
        out.append(lm)
    return out
