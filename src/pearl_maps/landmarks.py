"""Orientation landmarks from the curated reference file, best first.

The file is data/raw/landmarks.csv (edited by hand). Stage 01 validates it and
writes data/processed/landmarks.geojson; ``load_processed`` turns that into the
list the renderers pass to :func:`collect_landmarks`.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Point

# categories the renderers know about (the `category` column of landmarks.csv)
CATEGORIES = ("school", "health", "church", "maneaba", "gov", "community")
# lowest to highest; `min_confidence` in config.yaml keeps rows at or above one
CONFIDENCE_LEVELS = ("check", "medium", "high")


@dataclass(frozen=True)
class Landmark:
    name: str          # text printed on the map (the file's `label`)
    category: str      # school | health | church | maneaba | gov | community
    point: Point       # lon/lat
    priority: int      # lower prints first (config.yaml landmarks.priority)
    confidence: str    # check | medium | high


def collect_landmarks(landmarks: list[Landmark], bbox, max_name_len: int = 42) -> list[Landmark]:
    """Landmarks inside ``bbox`` (minx, miny, maxx, maxy in lon/lat), best first.

    ``landmarks`` is already ordered best-first by ``load_processed``. A name is
    used once per call, and names too long to print are skipped.
    """
    minx, miny, maxx, maxy = bbox
    seen: set[str] = set()
    out: list[Landmark] = []
    for lm in landmarks:
        if not (minx <= lm.point.x <= maxx and miny <= lm.point.y <= maxy):
            continue
        k = lm.name.lower()
        if k in seen or len(lm.name) > max_name_len:
            continue
        seen.add(k)
        out.append(lm)
    return out
