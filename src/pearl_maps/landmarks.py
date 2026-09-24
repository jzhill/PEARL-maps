"""Orientation landmarks from the curated reference file, best first.

The file is data/raw/landmarks.csv (edited by hand). Stage 01 validates it and
writes data/processed/landmarks.geojson; ``load_processed`` turns that into the
list the renderers pass to :func:`collect_landmarks`.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point

# categories the renderers know about (the `category` column of landmarks.csv)
CATEGORIES = ("school", "health", "church", "maneaba", "gov", "business", "community")
# lowest to highest; `min_confidence` in config.yaml keeps rows at or above one
CONFIDENCE_LEVELS = ("check", "medium", "high")
SAME_SPOT_DEG = 0.0003     # ~30 m: two rows with one name this close are the same place


@dataclass(frozen=True)
class Landmark:
    name: str          # text printed on the map (the file's `label`)
    category: str      # school | health | church | maneaba | gov | business | community
    point: Point       # lon/lat
    priority: int      # lower prints first (config.yaml landmarks.priority)
    confidence: str    # check | medium | high


def collect_landmarks(landmarks: list[Landmark], bbox, max_name_len: int = 42) -> list[Landmark]:
    """Landmarks inside ``bbox`` (minx, miny, maxx, maxy in lon/lat), best first.

    ``landmarks`` is already ordered best-first by ``load_processed``. Names too
    long to print are skipped. The same name may appear more than once (several
    shops of one chain, several churches of one denomination), but a repeat within
    ``SAME_SPOT_DEG`` of an earlier one is a duplicate row and is skipped.
    """
    minx, miny, maxx, maxy = bbox
    out: list[Landmark] = []
    for lm in landmarks:
        if not (minx <= lm.point.x <= maxx and miny <= lm.point.y <= maxy):
            continue
        if len(lm.name) > max_name_len:
            continue
        if any(o.name.lower() == lm.name.lower() and o.point.distance(lm.point) < SAME_SPOT_DEG
               for o in out):
            continue
        out.append(lm)
    return out
