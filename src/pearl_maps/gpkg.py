"""Minimal read-only GeoPackage reader.

A GeoPackage is a SQLite database. Each feature table has an R-tree index
(``rtree_<table>_<geomcol>``), so a bounding-box query is a plain SQL join.
Geometry blobs are a short GeoPackage header followed by standard WKB, which
Shapely parses. This avoids a GDAL / GeoPandas dependency entirely.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from shapely import wkb
from shapely.geometry.base import BaseGeometry

# bytes of envelope that follow the 8-byte header, by envelope indicator
_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}

BBox = tuple[float, float, float, float]   # minx, miny, maxx, maxy (lon/lat)


def parse_geometry(blob: bytes | None) -> BaseGeometry | None:
    if blob is None:
        return None
    if blob[:2] != b"GP":                      # plain WKB
        return wkb.loads(blob)
    flags = blob[3]
    if (flags >> 4) & 0x01:                    # empty-geometry flag
        return None
    envelope = (flags >> 1) & 0x07
    return wkb.loads(blob[8 + _ENVELOPE_BYTES[envelope]:])


class GeoPackage:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self._con.row_factory = sqlite3.Row
        self._geom_cols: dict[str, str] = {}

    def layers(self) -> list[str]:
        rows = self._con.execute(
            "select table_name from gpkg_contents where data_type='features'")
        return [r[0] for r in rows]

    def _geom_col(self, table: str) -> str:
        if table not in self._geom_cols:
            row = self._con.execute(
                "select column_name from gpkg_geometry_columns where table_name=?",
                (table,)).fetchone()
            self._geom_cols[table] = row[0] if row else "geom"
        return self._geom_cols[table]

    def query(self, table: str, bbox: BBox | None = None,
              columns: tuple[str, ...] = ()) -> list[tuple[BaseGeometry, dict]]:
        """Features of ``table`` whose envelope intersects ``bbox``."""
        gc = self._geom_col(table)
        sql = f"select {', '.join(['fid', gc, *columns])} from {table}"
        args: tuple = ()
        if bbox is not None:
            minx, miny, maxx, maxy = bbox
            sql += (f" where fid in (select id from rtree_{table}_{gc}"
                    " where maxx>=? and minx<=? and maxy>=? and miny<=?)")
            args = (minx, maxx, miny, maxy)
        out = []
        for row in self._con.execute(sql, args):
            g = parse_geometry(row[gc])
            if g is None or g.is_empty:
                continue
            out.append((g, {c: row[c] for c in columns}))
        return out
