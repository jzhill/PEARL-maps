"""Matplotlib drawing primitives. All coordinates are page millimetres."""
from __future__ import annotations

import math

from matplotlib.collections import LineCollection
from matplotlib.patches import PathPatch, Polygon as MplPolygon, Rectangle
from matplotlib.path import Path as MplPath
from shapely.geometry.base import BaseGeometry

from .geometry import PageTransform
from .labels import Grid, font_family, text_width_mm
from .style import (LANDUSE_FILL, ROAD_CLASS, ROAD_EDGE_KEY, ROAD_FILL_KEY,
                    ROAD_MIN_MM, ROAD_ORDER, ROAD_WIDTH_M)

MM_TO_PT = 72.0 / 25.4


# ---------------------------------------------------------------- shapely -> mpl

def polygons(g: BaseGeometry) -> list:
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [p for p in g.geoms if p.geom_type == "Polygon"]
    return []


def poly_patches(geoms, **kw) -> list[PathPatch]:
    out = []
    for g in geoms:
        for p in polygons(g):
            verts, codes = [], []
            for ring in [p.exterior, *p.interiors]:
                cs = list(ring.coords)
                verts.extend(cs)
                codes.extend([MplPath.MOVETO] + [MplPath.LINETO] * (len(cs) - 2)
                             + [MplPath.CLOSEPOLY])
            out.append(PathPatch(MplPath(verts, codes), **kw))
    return out


def line_segs(geoms) -> list[list[tuple[float, float]]]:
    out = []
    for g in geoms:
        if g.is_empty:
            continue
        parts = g.geoms if hasattr(g, "geoms") else [g]
        for p in parts:
            if p.geom_type == "LineString":
                out.append(list(p.coords))
            elif p.geom_type == "Polygon":
                out.append(list(p.exterior.coords))
    return out


def dashed_outline(ax, geoms, lw, color, dash, zorder):
    segs = line_segs(geoms)
    if segs:
        ax.add_collection(LineCollection(segs, linewidths=lw, colors=color,
                                         linestyle=(0, dash), zorder=zorder))


# ---------------------------------------------------------------- basemap

def setup_axes(ax, w: float, h: float, background: str) -> None:
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_linewidth(0.6)
        s.set_color("#555555")
    ax.set_facecolor(background)


def draw_basemap(ax, osm, T: PageTransform, st: dict) -> list:
    """Land, beach, landuse, buildings and roads, clipped to the frame.
    Returns the road features (geometry, attrs) for later labelling."""
    bbox = T.lonlat_bbox()
    clip = T.clip

    def fill(geoms, colour, edge="none", lw=0.0, z=1):
        for p in poly_patches([T(g).intersection(clip) for g in geoms],
                              facecolor=colour, edgecolor=edge, linewidth=lw, zorder=z):
            ax.add_patch(p)

    fill([g for g, _ in osm.query("land", bbox)], st["land"], z=1)
    nat = osm.query("natural", bbox, ("natural",))
    fill([g for g, a in nat if a["natural"] in ("beach", "sand")], st["beach"], z=2)
    fill([g for g, a in nat if a["natural"] in ("water", "wetland")], st["water"], z=2)
    fill([g for g, a in nat if a["natural"] in ("wood", "scrub", "grassland")], st["grass"], z=2)
    lu = osm.query("landuse", bbox, ("landuse",))
    for value, key in LANDUSE_FILL.items():
        fill([g for g, a in lu if a["landuse"] == value], st[key], z=3)
    fill([g for g, _ in osm.query("buildings", bbox)], st["building"],
         edge=st["building_edge"], lw=st["building_lw"], z=4)

    roads = osm.query("highway_ln", bbox, ("highway", "name"))
    by_class: dict[str, list] = {}
    for g, a in roads:
        c = ROAD_CLASS.get(a["highway"])
        if c:
            by_class.setdefault(c, []).append(g)
    for c in ROAD_ORDER:
        if c not in by_class:
            continue
        segs = line_segs([T(g).intersection(clip) for g in by_class[c]])
        wpt = max(ROAD_WIDTH_M[c] * T.mm_per_m, ROAD_MIN_MM[c]) * MM_TO_PT
        if c != "track":   # casing under the fill
            ax.add_collection(LineCollection(segs, linewidths=wpt + 0.9,
                                             colors=st[ROAD_EDGE_KEY[c]], zorder=5,
                                             capstyle="round", joinstyle="round"))
        ax.add_collection(LineCollection(
            segs, linewidths=wpt, colors=st[ROAD_FILL_KEY[c]], zorder=5.1,
            capstyle="round", joinstyle="round",
            linestyle=(0, (2.2, 1.6)) if c == "track" else "solid"))

    # fade everything drawn so far, like a semi-transparent basemap layer
    if st["fade"] > 0:
        ax.add_patch(Rectangle((0, 0), T.w, T.h, facecolor="white", edgecolor="none",
                               alpha=st["fade"], zorder=5.6))
    return roads


# ---------------------------------------------------------------- decorations

def north_arrow(ax, x: float, y: float, rotation_deg: float, size: float = 8.5,
                zorder: float = 15) -> None:
    """Half-filled arrow pointing to true north on a map rotated by ``rotation_deg``."""
    d = math.radians(rotation_deg)
    nx, ny = -math.sin(d), math.cos(d)
    px, py = math.cos(d), math.sin(d)
    tip = (x + nx * size, y + ny * size)
    tail = (x - nx * size * 0.55, y - ny * size * 0.55)
    base = (x - nx * size * 0.15, y - ny * size * 0.15)
    left = (base[0] + px * size * 0.42, base[1] + py * size * 0.42)
    right = (base[0] - px * size * 0.42, base[1] - py * size * 0.42)
    ax.add_patch(MplPolygon([tip, left, tail], closed=True, fc="white", ec="black",
                            lw=0.7, zorder=zorder))
    ax.add_patch(MplPolygon([tip, right, tail], closed=True, fc="black", ec="black",
                            lw=0.7, zorder=zorder))
    ax.text(tip[0] + nx * size * 0.35, tip[1] + ny * size * 0.35, "N", ha="center",
            va="center", fontsize=8.5, fontweight="bold", fontfamily=font_family(),
            zorder=zorder)


def scale_bar(ax, x0: float, y: float, length_m: int, mm_per_m: float,
              zorder: float = 15) -> None:
    blen = length_m * mm_per_m
    ax.plot([x0, x0 + blen], [y, y], color="black", lw=1.0, zorder=zorder)
    for frac in (0.0, 0.5, 1.0):
        ax.plot([x0 + blen * frac] * 2, [y, y + 1.6], color="black", lw=1.0, zorder=zorder)
        ax.text(x0 + blen * frac, y + 2.2,
                f"{int(length_m * frac)}" + (" m" if frac == 1.0 else ""),
                ha="center", va="bottom", fontsize=8, fontfamily=font_family(),
                zorder=zorder)


def white_panel(ax, b, zorder: float = 11.8) -> None:
    ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], facecolor="white",
                           edgecolor="#777777", linewidth=0.5, zorder=zorder))


def text_along(ax, blocked: Grid, text: str, line, at: float, frame,
               size: float = 7.0, color: str = "#000000", zorder: float = 8) -> bool:
    """Text centred on ``line`` at distance ``at``, rotated to follow it, with a
    white knock-out. Skips (returns False) if it would overlap anything."""
    fw, fh = frame
    p = line.interpolate(at)
    q = line.interpolate(min(at + 2.5, line.length))
    r = line.interpolate(max(at - 2.5, 0))
    ang = math.degrees(math.atan2(q.y - r.y, q.x - r.x))
    ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
    w = text_width_mm(text, size)
    ca, sa = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
    bw, bh = w * ca + 3.2 * sa, w * sa + 3.2 * ca
    b = (p.x - bw / 2 - 0.5, p.y - bh / 2 - 0.5, p.x + bw / 2 + 0.5, p.y + bh / 2 + 0.5)
    if b[0] < 0.5 or b[1] < 0.5 or b[2] > fw - 0.5 or b[3] > fh - 0.5 or blocked.hits(b):
        return False
    blocked.add(b)
    ax.text(p.x, p.y, text, rotation=ang, rotation_mode="anchor", ha="center",
            va="center", fontsize=size, fontfamily=font_family(), color=color,
            zorder=zorder,
            bbox=dict(boxstyle="square,pad=0.12", fc="white", ec="none", alpha=0.85))
    return True
