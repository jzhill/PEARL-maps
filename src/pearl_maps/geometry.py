"""Projection and geometry helpers.

Maps are drawn in *page millimetres*. The chain is:

    lon/lat  --Proj-->  local metres (optionally rotated)  --PageTransform-->  mm

A local equirectangular projection is accurate to well under a metre at the
scale of one village near the equator, which is all these maps need.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely import affinity
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_EQ = 111_320.0


class Proj:
    """lon/lat -> metres about (lon0, lat0), then rotated anticlockwise by ``deg``."""

    def __init__(self, lon0: float, lat0: float, deg: float = 0.0):
        self.lon0, self.lat0 = lon0, lat0
        self.kx = M_PER_DEG_LON_EQ * math.cos(math.radians(lat0))
        self.ky = M_PER_DEG_LAT
        self.deg = deg
        r = math.radians(deg)
        self._c, self._s = math.cos(r), math.sin(r)

    def rotated(self, deg: float) -> "Proj":
        return Proj(self.lon0, self.lat0, deg)

    def fwd(self, lon: float, lat: float) -> tuple[float, float]:
        x = (lon - self.lon0) * self.kx
        y = (lat - self.lat0) * self.ky
        return x * self._c - y * self._s, x * self._s + y * self._c

    def inv(self, x: float, y: float) -> tuple[float, float]:
        xx = x * self._c + y * self._s
        yy = -x * self._s + y * self._c
        return self.lon0 + xx / self.kx, self.lat0 + yy / self.ky

    def geom(self, g: BaseGeometry) -> BaseGeometry:
        if g.is_empty:
            return g
        def f(xs, ys, zs=None):
            pts = [self.fwd(a, b) for a, b in zip(xs, ys)]
            return tuple(p[0] for p in pts), tuple(p[1] for p in pts)
        return transform(f, g)

    def geom_inv(self, g: BaseGeometry) -> BaseGeometry:
        def f(xs, ys, zs=None):
            pts = [self.inv(a, b) for a, b in zip(xs, ys)]
            return tuple(p[0] for p in pts), tuple(p[1] for p in pts)
        return transform(f, g)


@dataclass(frozen=True)
class PageTransform:
    """Projected metres -> page millimetres inside a map frame of size w x h."""
    proj: Proj
    cx: float          # frame centre in projected metres
    cy: float
    mm_per_m: float
    w: float           # frame size in mm
    h: float

    def __call__(self, g_ll: BaseGeometry) -> BaseGeometry:
        g = self.proj.geom(g_ll)
        g = affinity.translate(g, -self.cx, -self.cy)
        g = affinity.scale(g, self.mm_per_m, self.mm_per_m, origin=(0, 0))
        return affinity.translate(g, self.w / 2, self.h / 2)

    def point(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = self.proj.fwd(lon, lat)
        return ((x - self.cx) * self.mm_per_m + self.w / 2,
                (y - self.cy) * self.mm_per_m + self.h / 2)

    @property
    def clip(self) -> BaseGeometry:
        return box(0, 0, self.w, self.h)

    @property
    def scale_denominator(self) -> int:
        return round(1000.0 / self.mm_per_m)

    def lonlat_bbox(self, pad_deg: float = 0.0006) -> tuple[float, float, float, float]:
        gw, gh = self.w / self.mm_per_m, self.h / self.mm_per_m
        corners = [(self.cx + sx * gw / 2, self.cy + sy * gh / 2)
                   for sx in (-1, 1) for sy in (-1, 1)]
        lls = [self.proj.inv(*c) for c in corners]
        return (min(p[0] for p in lls) - pad_deg, min(p[1] for p in lls) - pad_deg,
                max(p[0] for p in lls) + pad_deg, max(p[1] for p in lls) + pad_deg)


def long_axis_deg(g_proj: BaseGeometry) -> float:
    """Angle (deg) of the long side of the minimum rotated rectangle."""
    rect = g_proj.minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    edges = sorted(((xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(4)),
                   key=lambda e: -(e[0] ** 2 + e[1] ** 2))
    return math.degrees(math.atan2(edges[0][1], edges[0][0]))


def trim_to_land(poly_ll: BaseGeometry, osm) -> BaseGeometry:
    """Drop lagoon / ocean parts of an EA before sizing the map, so a boundary
    drawn out over the reef does not shrink the print scale."""
    b = poly_ll.bounds
    land = unary_union([g for g, _ in osm.query(
        "land", (b[0] - 0.002, b[1] - 0.002, b[2] + 0.002, b[3] + 0.002))])
    if land.is_empty:
        return poly_ll
    keep = poly_ll.intersection(land.buffer(0.00025))
    if keep.is_empty or keep.area < poly_ll.area * 0.15:
        return poly_ll
    return keep


def split_bands(target_ll: BaseGeometry, pts_ll: list[tuple[float, float]], n: int,
                overlap_m: float = 25.0) -> list[BaseGeometry]:
    """Cut an EA into ``n`` bands across its long axis, each holding about the
    same number of households, overlapping by ``overlap_m`` so none fall in a gap.
    Returns lon/lat polygons."""
    c = target_ll.centroid
    pr = Proj(c.x, c.y, 0.0)
    pr = pr.rotated(-long_axis_deg(pr.geom(target_ll)))     # long axis horizontal
    us = sorted(pr.fwd(lon, lat)[0] for lon, lat in pts_ll)
    minx, miny, maxx, maxy = pr.geom(target_ll).bounds
    cuts = [us[int(len(us) * k / n)] for k in range(1, n)]
    edges = [minx - 50.0, *cuts, maxx + 50.0]
    bands = []
    for k in range(n):
        lo = edges[k] - (overlap_m if k else 0.0)
        hi = edges[k + 1] + (overlap_m if k < n - 1 else 0.0)
        bands.append(pr.geom_inv(box(lo, miny - 60.0, hi, maxy + 60.0)))
    return bands
