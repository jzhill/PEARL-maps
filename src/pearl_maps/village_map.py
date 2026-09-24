"""Village orientation sheets: every EA boundary and number in one village,
over roads, landmarks and household density - no household names.

Atoll villages are long thin strips, so the A4 landscape sheet holds one to
``max_panels`` stacked strip panels running west to east, whichever gives the
largest print scale.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from shapely.geometry import box
from shapely.ops import unary_union

from .config import Config
from .data import Datasets
from .draw import (dashed_outline, draw_basemap, north_arrow, scale_bar, setup_axes,
                   text_along)
from .geometry import PageTransform, Proj, long_axis_deg, trim_to_land
from .labels import (Grid, Label, font_family, place_first_fit, text_height_mm,
                     text_width_mm, use_font)
from .landmarks import collect_landmarks
from .layout import A4_LANDSCAPE, MARGIN, nice_scalebar_m
from .style import ROAD_CLASS, STYLES

MM = 1 / 25.4
PANEL_GAP_MM = 6.0
LEGEND_BAND_MM = 34.0
PAD_M = 30.0


@dataclass
class VillageResult:
    file: Path
    village: str
    eas: int
    ea_labels: int
    landmarks: int
    households: int
    panels: int
    rotation: float
    scale: int

    def row(self) -> dict:
        return dict(village=self.village, file=self.file.name, eas=self.eas,
                    ea_labels=self.ea_labels, landmarks=self.landmarks,
                    households=self.households, panels=self.panels,
                    rotation=self.rotation, scale=f"1:{self.scale}")


VILLAGE_LOG_FIELDS = list(VillageResult(Path("x"), "", 0, 0, 0, 0, 0, 0, 0).row())


def common_prefix(ids: list[str], keep: int = 5) -> str:
    """Shared leading digits, used to shorten EA numbers on the sheet."""
    p = ids[0]
    for s in ids[1:]:
        while not s.startswith(p):
            p = p[:-1]
    return p[:keep]


class VillageMapRenderer:
    def __init__(self, cfg: Config, ds: Datasets, style: str | None = None):
        self.cfg, self.ds = cfg, ds
        self.opt = cfg.village_map
        self.st = STYLES[style or cfg.ea_map["style"]]
        use_font(cfg.ea_map["fonts"])

    # ------------------------------------------------------------ public

    def render(self, village: str, out_pdf: Path) -> VillageResult:
        ea_ids = self.ds.village_eas(village)
        if not ea_ids:
            raise ValueError(f"no mappable EAs for village {village!r}")
        prefix = common_prefix(ea_ids)
        target = trim_to_land(unary_union([self.ds.eas[e].geom for e in ea_ids]),
                              self.ds.osm)

        page = A4_LANDSCAPE
        fw = page[0] - MARGIN["left"] - MARGIN["right"]
        avail_h = page[1] - MARGIN["top"] - MARGIN["bottom"] - LEGEND_BAND_MM
        n, ph, proj, (minx, miny, maxx, maxy), mm_per_m = self._choose_panels(
            target, fw, avail_h)
        span = (maxx - minx) + 2 * PAD_M
        cy = (miny + maxy) / 2

        fig = plt.figure(figsize=(page[0] * MM, page[1] * MM))
        top = page[1] - MARGIN["top"]
        n_ea = n_lm = 0
        for k in range(n):
            y_top = top - k * (ph + PANEL_GAP_MM)
            ax = fig.add_axes([MARGIN["left"] / page[0], (y_top - ph) / page[1],
                               fw / page[0], ph / page[1]])
            cx = (minx - PAD_M) + span * (k + 0.5) / n
            T = PageTransform(proj, cx, cy, mm_per_m, fw, ph)
            a, b = self._panel(ax, T, ea_ids, prefix, f"{k + 1} of {n}" if n > 1 else None)
            n_ea += a
            n_lm += b

        fig.text(0.5, 1 - 8.0 / page[1],
                 f"{village.replace('_', ' ')} — EA orientation map",
                 ha="center", va="top", fontsize=16, fontfamily=font_family())
        n_hh = len(self.ds.households_in(ea_ids))
        band_top = top - n * ph - (n - 1) * PANEL_GAP_MM - 2.0
        self._legend_band(fig, page, band_top, village, prefix, len(ea_ids), n_hh, n,
                          mm_per_m, proj.deg, fw)
        fig.savefig(out_pdf)
        plt.close(fig)
        return VillageResult(out_pdf, village, len(ea_ids), n_ea, n_lm, n_hh, n,
                             round(proj.deg, 1), round(1000 / mm_per_m))

    # ------------------------------------------------------------ layout

    def _choose_panels(self, target, fw, avail_h):
        c = target.centroid
        base = Proj(c.x, c.y)
        best = None
        for deg in (0.0, -long_axis_deg(base.geom(target))):
            pr = base.rotated(deg)
            minx, miny, maxx, maxy = pr.geom(target).bounds
            W, H = maxx - minx + 2 * PAD_M, maxy - miny + 2 * PAD_M
            for n in range(1, int(self.opt["max_panels"]) + 1):
                ph = (avail_h - PANEL_GAP_MM * (n - 1)) / n
                m = min(fw / (W / n), ph / H)
                score = m / (1.0 if abs(deg) < 1e-6 else 1.08)
                if best is None or score > best[0]:
                    best = (score, n, ph, pr, (minx, miny, maxx, maxy), m)
        return best[1:]

    # ------------------------------------------------------------ one panel

    def _panel(self, ax, T: PageTransform, ea_ids, prefix, badge):
        st = self.st
        fw, fh, clip = T.w, T.h, T.clip
        setup_axes(ax, fw, fh, st["water"])
        roads = draw_basemap(ax, self.ds.osm, T, st)
        blocked = Grid()
        frame_ll = box(*T.lonlat_bbox())
        fset = set(ea_ids)

        if badge:
            ax.text(1.4, fh - 1.4, badge, ha="left", va="top", fontsize=7.5,
                    fontweight="bold", fontfamily=font_family(), zorder=16,
                    bbox=dict(boxstyle="square,pad=0.25", fc="white", ec="#555555", lw=0.4))
            blocked.add((0.0, fh - 6.5, text_width_mm(badge, 7.5, True) + 5.0, fh))

        others = [T(v.geom).intersection(clip) for e, v in self.ds.eas.items()
                  if e not in fset and v.geom.intersects(frame_ll)]
        dashed_outline(ax, others, 0.55, "#9a9a9a", (3, 2.4), 6)

        if self.opt["show_households"]:
            xs, ys = [], []
            for h in self.ds.households:
                if h.in_scope:
                    x, y = T.point(h.lon, h.lat)
                    if 0 <= x <= fw and 0 <= y <= fh:
                        xs.append(x); ys.append(y)
            ax.plot(xs, ys, ls="none", marker="o", ms=1.4, mfc="#7d7d7d", mec="none",
                    zorder=8)

        polys = {e: T(self.ds.eas[e].geom).buffer(0) for e in ea_ids}
        polys = {e: g for e, g in polys.items() if g.intersects(clip)}
        dashed_outline(ax, [g.intersection(clip) for g in polys.values()], 1.5,
                       st["ea_line"], (4.5, 2.2), 9)

        # road names
        named: dict[str, list] = {}
        for g, a in roads:
            if ROAD_CLASS.get(a["highway"]) in ("main", "sec") and a["name"]:
                named.setdefault(a["name"].strip(), []).append(g)
        for name, gs in list(named.items())[:5]:
            merged = unary_union([T(g) for g in gs]).intersection(clip)
            parts = [p for p in getattr(merged, "geoms", [merged])
                     if p.geom_type == "LineString" and p.length > 40]
            for p in sorted(parts, key=lambda p: -p.length)[:2]:
                for frac in (0.5, 0.25, 0.75):
                    if text_along(ax, blocked, name, p, p.length * frac, (fw, fh),
                                  size=7.0, color="#333333", zorder=12):
                        break

        # landmarks
        chosen = []
        for lm in collect_landmarks(self.ds.landmarks, T.lonlat_bbox(0.0008), max_name_len=40):
            x, y = T.point(lm.point.x, lm.point.y)
            if 2 <= x <= fw - 2 and 2 <= y <= fh - 2:
                chosen.append((lm, x, y))
            if len(chosen) >= int(self.opt["landmarks_per_panel"]):
                break
        for lm, x, y in chosen:
            blocked.add((x - 1.3, y - 1.3, x + 1.3, y + 1.3))
            ax.plot([x], [y], marker="*", ms=6.5, mfc=st["landmark"], mec=st["landmark"],
                    mew=0.4, ls="none", zorder=11)
        n_lm = 0
        for lm, x, y in chosen:
            L = Label(lm.name, x, y, text_width_mm(lm.name, 7.0, True), text_height_mm(7.0))
            if place_first_fit(L, (fw, fh), blocked, pad=0.4, max_ring=9.0):
                ax.text(L.tx, L.ty, L.text, ha=L.ha, va="center", fontsize=7.0,
                        fontweight="bold", fontfamily=font_family(),
                        color=st["landmark_text"], zorder=12)
                n_lm += 1

        # EA numbers, shortened, inside their own EA where possible (smallest first)
        n_ea = 0
        for e, g in sorted(polys.items(), key=lambda kv: kv[1].intersection(clip).area):
            gi = g.intersection(clip)
            if gi.is_empty or gi.area < 1.0:
                continue
            c = gi.centroid
            anchor = c if gi.contains(c) else gi.representative_point()
            t = e[len(prefix):]
            L = Label(t, anchor.x, anchor.y, text_width_mm(t, 8.0, True), text_height_mm(8.0))
            if (place_first_fit(L, (fw, fh), blocked, pad=0.35, max_ring=6.0,
                                allowed=g.buffer(1.0))
                    or place_first_fit(L, (fw, fh), blocked, pad=0.35, max_ring=9.0)):
                ax.text(L.tx, L.ty, t, ha=L.ha, va="center", fontsize=8.0,
                        fontweight="bold", fontfamily=font_family(), color="#000000",
                        zorder=13,
                        bbox=dict(boxstyle="square,pad=0.18", fc="white", ec="#555555",
                                  lw=0.4, alpha=0.95))
                n_ea += 1
        return n_ea, n_lm

    # ------------------------------------------------------------ legend band

    def _legend_band(self, fig, page, band_top, village, prefix, n_eas, n_hh, n_panels,
                     mm_per_m, rotation, fw):
        st = self.st
        y0 = MARGIN["bottom"] + 4.0
        h = max(band_top - y0, 14.0)
        ax = fig.add_axes([MARGIN["left"] / page[0], y0 / page[1], fw / page[0], h / page[1]])
        ax.set_xlim(0, fw)
        ax.set_ylim(0, h)
        ax.axis("off")
        f = font_family()
        yv = h - 3.0
        vname = village.replace("_", " ")
        ax.add_collection(LineCollection([[(1.0, yv), (9.0, yv)]], linewidths=1.5,
                                         colors="black", linestyle=(0, (4.5, 2.2))))
        ax.text(10.5, yv, f"EA boundary — {vname}", va="center", fontsize=7.2, fontfamily=f)
        ax.add_collection(LineCollection([[(66.0, yv), (74.0, yv)]], linewidths=0.55,
                                         colors="#9a9a9a", linestyle=(0, (3, 2.4))))
        ax.text(75.5, yv, "EA boundary — other villages", va="center", fontsize=7.2,
                fontfamily=f)
        ax.plot([135.0], [yv], marker="o", ms=1.8, mfc="#7d7d7d", mec="none", ls="none")
        ax.text(138.0, yv, "occupied household", va="center", fontsize=7.2, fontfamily=f)
        ax.plot([182.0], [yv], marker="*", ms=6.5, mfc=st["landmark"], mec=st["landmark"],
                ls="none")
        ax.text(185.0, yv, "landmark", va="center", fontsize=7.2, fontfamily=f)

        bar_m = nice_scalebar_m(mm_per_m, fw)
        bx0 = fw - bar_m * mm_per_m - 2.0
        yb = yv - 13.0
        scale_bar(ax, bx0, yb, bar_m, mm_per_m)
        north_arrow(ax, bx0 - 13.0, yb + 2.4, rotation, size=5.0)

        strip = (f"Panels run west to east; EA numbers omit the leading {prefix}."
                 if n_panels > 1 else f"EA numbers omit the leading {prefix}.")
        ax.text(0, yv - 8.0,
                f"{n_eas} enumeration areas  ·  {n_hh} occupied private households"
                f"  ·  1:{round(1000 / mm_per_m):,}\n{strip}",
                va="top", ha="left", fontsize=7.2, fontfamily=f)
        src = self.cfg.sources
        fig.text(MARGIN["left"] / page[0], 3.5 / page[1],
                 f"EA boundaries: {src['ea_boundaries']} · households: {src['households']}"
                 f" · base: {src['basemap']}",
                 ha="left", va="bottom", fontsize=6.0, fontfamily=f, color="#444444")
