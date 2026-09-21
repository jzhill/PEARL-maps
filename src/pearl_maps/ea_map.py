"""EA enumeration maps: one EA per A4 page, every household head named.

For each EA the renderer:

1. sizes the page to the EA (lagoon trimmed) plus its households, trying
   north-up first and a rotated layout only if it buys a larger font;
2. draws the basemap, the EA boundary (heavy dashed) and neighbouring
   boundaries (light dashed) with EA numbers set along each shared edge;
3. reserves a corner for the north arrow and scale bar, places landmarks;
4. seats every household name without overlap, stepping the font down
   through ``label_sizes_pt``; focus-EA names stay inside the EA or over open
   water; neighbours are named only near the boundary, smaller and in grey;
5. if the smallest font still fails - or only fits below the largest font -
   splits the EA across pages (``a``, ``b``, ...) along its long axis.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("pdf")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.collections import LineCollection
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep

from .config import Config
from .data import Datasets, Household
from .draw import (dashed_outline, draw_basemap, line_segs, north_arrow, scale_bar,
                   setup_axes, text_along, white_panel)
from .geometry import split_bands, trim_to_land
from .labels import (Grid, Label, font_family, place_first_fit, place_labels,
                     text_height_mm, text_width_mm, use_font)
from .landmarks import collect_landmarks
from .layout import MARGIN, Layout, frame_rect, layout_options, nice_scalebar_m
from .style import STYLES

MM = 1 / 25.4
SUFFIXES = "abcdefgh"


@dataclass
class PageResult:
    file: Path
    ea_ids: list[str]
    font_pt: float
    relaxed: bool
    names_placed: int
    names_total: int
    neighbours_named: int
    neighbours_total: int
    neighbours_unnamed: int
    orientation: str
    rotation: float
    scale: int
    part: int = 1
    parts: int = 1

    @property
    def complete(self) -> bool:
        return self.names_placed == self.names_total

    def row(self) -> dict:
        return dict(ea_id="-".join(self.ea_ids), file=self.file.name, part=self.part,
                    parts=self.parts, font_pt=self.font_pt, relaxed=int(self.relaxed),
                    names_placed=self.names_placed, names_total=self.names_total,
                    neighbours_named=self.neighbours_named,
                    neighbours_unnamed=self.neighbours_unnamed,
                    orientation=self.orientation, rotation=self.rotation,
                    scale=f"1:{self.scale}", complete=int(self.complete))


LOG_FIELDS = list(PageResult(Path("x"), [], 0, False, 0, 0, 0, 0, 0, "", 0, 0).row())


class EAMapRenderer:
    def __init__(self, cfg: Config, ds: Datasets, style: str | None = None,
                 verbose: bool = False):
        self.cfg, self.ds = cfg, ds
        self.opt = cfg.ea_map
        self.st = STYLES[style or self.opt["style"]]
        self.sizes = [float(s) for s in self.opt["label_sizes_pt"]]
        self.verbose = verbose
        use_font(self.opt["fonts"])

    # ------------------------------------------------------------ public

    def render(self, ea_ids: list[str], out_dir: Path, stem: str) -> list[PageResult]:
        """Render one EA (or a group printed together), splitting if needed."""
        out_dir.mkdir(parents=True, exist_ok=True)
        single_pdf = out_dir / f"{stem}.pdf"
        single = self._render_best_layout(ea_ids, single_pdf)
        if single.complete and single.font_pt >= self.sizes[0]:
            return [single]

        # try splitting; keep the single page if splitting does not help
        keep = None
        if single.complete:
            keep = out_dir / f"{stem}__single.pdf"
            os.replace(single_pdf, keep)
        else:
            single_pdf.unlink()

        fpoly = unary_union([self.ds.eas[e].geom for e in ea_ids])
        pts = [(h.lon, h.lat) for h in self.ds.households_in(ea_ids)]
        target = unary_union([fpoly] + [Point(p).buffer(2e-5) for p in pts])
        pages: list[PageResult] = []
        for n in range(2, int(self.opt["max_parts"]) + 1):
            bands = split_bands(target, pts, n, float(self.opt["split_overlap_m"]))
            pages = []
            for k, band in enumerate(bands):
                pdf = out_dir / f"{stem}{SUFFIXES[k]}.pdf"
                title = (f"{'-'.join(ea_ids)}{SUFFIXES[k]} - enumeration map "
                         f"(part {k + 1} of {n})")
                r = self._render_best_layout(ea_ids, pdf, sub=band, title=title)
                r.part, r.parts = k + 1, n
                pages.append(r)
            if all(p.complete for p in pages):
                if keep and min(p.font_pt for p in pages) <= single.font_pt:
                    break                              # no gain: use the single page
                if keep:
                    keep.unlink()
                return pages
            if n < int(self.opt["max_parts"]):
                for p in pages:
                    p.file.unlink(missing_ok=True)

        if keep:
            for p in pages:
                p.file.unlink(missing_ok=True)
            os.replace(keep, single_pdf)
            single.file = single_pdf
            return [single]
        return pages                                   # best effort; log shows incomplete

    # ------------------------------------------------------------ one page

    def _target(self, ea_ids, sub) -> tuple[BaseGeometry, list[Household]]:
        fpoly = unary_union([self.ds.eas[e].geom for e in ea_ids])
        fhh = self.ds.households_in(ea_ids)
        if sub is not None:
            fhh = [h for h in fhh if sub.contains(Point(h.lon, h.lat))]
            fpoly = fpoly.intersection(sub)
        fpoly = trim_to_land(fpoly, self.ds.osm)
        target = unary_union([fpoly] + [Point(h.lon, h.lat).buffer(2e-5) for h in fhh])
        return target, fhh

    def _render_best_layout(self, ea_ids, out_pdf: Path, sub=None, title=None) -> PageResult:
        target, fhh = self._target(ea_ids, sub)
        best = None
        for k, lay in enumerate(layout_options(target, float(self.opt["north_up_preference"]))):
            pdf = out_pdf if k == 0 else out_pdf.with_name(f"{out_pdf.stem}__try{k}.pdf")
            r = self._render_page(ea_ids, fhh, lay, pdf, sub, title)
            score = (-r.font_pt, r.names_total - r.names_placed, -r.neighbours_named)
            if best is None or score < best[0]:
                if best is not None and best[1].file != out_pdf:
                    best[1].file.unlink(missing_ok=True)
                best = (score, r)
            elif r.file != out_pdf:
                r.file.unlink(missing_ok=True)
            if r.complete and r.font_pt >= self.sizes[0]:
                break
        r = best[1]
        if r.file != out_pdf:
            os.replace(r.file, out_pdf)
            r.file = out_pdf
        return r

    def _render_page(self, ea_ids, fhh: list[Household], lay: Layout, out_pdf: Path,
                     sub, title) -> PageResult:
        st, T = self.st, lay.transform
        fw, fh = T.w, T.h
        clip = T.clip
        page = lay.page
        fx, fy, _, _ = frame_rect(page)
        fig = plt.figure(figsize=(page[0] * MM, page[1] * MM))
        ax = fig.add_axes([fx / page[0], fy / page[1], fw / page[0], fh / page[1]])
        setup_axes(ax, fw, fh, st["water"])
        draw_basemap(ax, self.ds.osm, T, st)

        # ---- boundaries
        fset = set(ea_ids)
        frame_ll = box(*T.lonlat_bbox())
        focus_mm = unary_union([T(self.ds.eas[e].geom) for e in ea_ids]).buffer(0)
        others = [(e, T(v.geom).buffer(0)) for e, v in self.ds.eas.items()
                  if e not in fset and v.geom.intersects(frame_ll)]
        others = [(e, g) for e, g in others if g.intersects(clip)]
        union_other = unary_union([g for _, g in others]) if others else None
        dashed_outline(ax, [g.intersection(clip) for _, g in others], 0.9, st["ea_other"],
                       (4.5, 2.6), 6)
        dashed_outline(ax, [focus_mm.intersection(clip)], 2.1, st["ea_line"], (4.0, 2.4), 7)
        if sub is not None:                              # where a split page continues
            dashed_outline(ax, [T(sub).boundary.intersection(clip)], 1.2, "#666666",
                           (6, 2, 1, 2), 6.5)

        blocked = Grid()

        # ---- households in frame
        fkeys = {h.idx for h in fhh}
        focus_pts, other_pts = [], []
        for h in self.ds.households:
            if not h.in_scope:
                continue
            x, y = T.point(h.lon, h.lat)
            if 0 <= x <= fw and 0 <= y <= fh:
                (focus_pts if h.idx in fkeys else other_pts).append((x, y, h))
        all_pts = focus_pts + other_pts

        # ---- reserve the emptiest corner for north arrow + scale bar
        bar_m = nice_scalebar_m(T.mm_per_m, fw)
        dec_w, dec_h = max(34.0, bar_m * T.mm_per_m + 8.0), 27.0
        corners = [(fw - dec_w - 1, fh - dec_h - 1), (1, fh - dec_h - 1),
                   (fw - dec_w - 1, 1), (1, 1)]
        def crowding(c):
            x0, y0 = c
            return sum(1 for x, y, _ in all_pts
                       if x0 - 6 < x < x0 + dec_w + 6 and y0 - 6 < y < y0 + dec_h + 6)
        cx0, cy0 = min(corners, key=crowding)
        deco = (cx0, cy0, cx0 + dec_w, cy0 + dec_h)
        blocked.add(deco)

        # ---- EA numbers on the boundary
        self._label_boundaries(ax, blocked, focus_mm, others, ea_ids, clip, (fw, fh))

        # ---- landmarks
        self._landmarks(ax, blocked, T, (fw, fh))

        # ---- household markers (never moved)
        for x, y, _ in all_pts:
            blocked.add((x - 0.75, y - 0.75, x + 0.75, y + 0.75))
        ax.plot([p[0] for p in all_pts], [p[1] for p in all_pts], ls="none", marker="+",
                ms=3.6, mew=0.75, color=st["hh_marker"], zorder=9)

        # ---- household names
        halo = prep(focus_mm.buffer(float(self.opt["neighbour_halo_mm"])))
        named_neighbours = [p for p in other_pts if halo.contains(Point(p[0], p[1]))]
        free = clip.difference(union_other) if union_other is not None else clip
        allowed = {False: unary_union([focus_mm.buffer(2.0), free]),
                   True: unary_union([focus_mm.buffer(8.0), free])}
        forbidden = focus_mm.buffer(-0.4)
        step = float(self.opt["neighbour_size_step_pt"])

        chosen = None
        for relaxed in (False, True):
            for size in self.sizes:
                nsize = max(self.sizes[-1], size - step)
                labs = []
                for x, y, h in focus_pts:
                    if h.label:
                        labs.append(Label(h.label, x, y, text_width_mm(h.label, size),
                                          text_height_mm(size), True, size))
                for x, y, h in named_neighbours:
                    if h.label:
                        labs.append(Label(h.label, x, y, text_width_mm(h.label, nsize),
                                          text_height_mm(nsize), False, nsize))
                place_labels(labs, (fw, fh), blocked, allowed[relaxed], forbidden,
                             max_ring_focus=float(self.opt["max_displacement_mm"]))
                n_f = sum(1 for L in labs if L.focus)
                ok = sum(1 for L in labs if L.focus and L.placed)
                if self.verbose:
                    print(f"      {size:4.1f}pt{' relaxed' if relaxed else ''}: {ok}/{n_f}")
                if chosen is None or ok > chosen[2]:
                    chosen = (size, labs, ok, n_f, relaxed)
                if ok == n_f:
                    break
            if chosen[2] == chosen[3]:
                break
        size, labs, ok, n_f, relaxed = chosen
        for L in labs:
            if L.placed:
                ax.text(L.tx, L.ty, L.text, ha=L.ha, va="center", fontsize=L.size_pt,
                        fontfamily=font_family(),
                        color=st["hh_text"] if L.focus else st["hh_text_neighbour"],
                        zorder=11 if L.focus else 10.5,
                        path_effects=[pe.withStroke(linewidth=1.4, foreground="white",
                                                    alpha=0.75)])

        # ---- north arrow + scale bar
        white_panel(ax, deco)
        north_arrow(ax, (deco[0] + deco[2]) / 2, deco[1] + 15.5, lay.rotation, zorder=12)
        scale_bar(ax, (deco[0] + deco[2]) / 2 - bar_m * T.mm_per_m / 2, deco[1] + 4.2,
                  bar_m, T.mm_per_m, zorder=12)

        # ---- title + footer
        W, H = page
        fig.text(0.5, 1 - 9.0 / H, title or f"{'-'.join(ea_ids)} - enumeration map",
                 ha="center", va="top", fontsize=17, fontfamily=font_family())
        src = self.cfg.sources
        village = self.ds.eas[ea_ids[0]].village
        fig.text(MARGIN["left"] / W, 4.0 / H,
                 f"{village} · {len(focus_pts)} occupied private households · "
                 f"EA boundaries: {src['ea_boundaries']} · households: "
                 f"{src['households']} · base: {src['basemap']}",
                 ha="left", va="bottom", fontsize=6.0, fontfamily=font_family(),
                 color="#444444")
        fig.savefig(out_pdf)
        plt.close(fig)

        return PageResult(
            file=out_pdf, ea_ids=list(ea_ids), font_pt=size, relaxed=relaxed,
            names_placed=ok, names_total=n_f,
            neighbours_named=sum(1 for L in labs if not L.focus and L.placed),
            neighbours_total=sum(1 for L in labs if not L.focus),
            neighbours_unnamed=len(other_pts) - len(named_neighbours),
            orientation=lay.orientation, rotation=round(lay.rotation, 1),
            scale=T.scale_denominator)

    # ------------------------------------------------------------ helpers

    def _label_boundaries(self, ax, blocked, focus_mm, others, ea_ids, clip, frame):
        """Neighbour EA numbers on each shared edge; the focus EA number repeated
        along its own boundary."""
        colour = self.st["ea_line"]
        fb = focus_mm.boundary
        for e, g in others:
            shared = fb.intersection(g.buffer(0.4)).intersection(clip)
            parts = [p for p in getattr(shared, "geoms", [shared])
                     if p.geom_type == "LineString" and p.length > 8]
            for p in sorted(parts, key=lambda p: -p.length)[:2]:
                for shift in (0, 14, -14, 28, -28):
                    d = p.length / 2 + shift
                    if 4 < d < p.length - 4 and text_along(ax, blocked, e, p, d, frame,
                                                           color=colour):
                        break
        own = fb.intersection(clip)
        label = ea_ids[0]
        for p in [p for p in getattr(own, "geoms", [own]) if p.geom_type == "LineString"]:
            if p.length < 18:
                continue
            n = min(3, max(1, int(p.length // 110)))
            for k in range(n):
                base = p.length * (k + 0.5) / n
                for shift in (0, 12, -12, 24, -24, 40, -40):
                    d = base + shift
                    if 4 < d < p.length - 4 and text_along(ax, blocked, label, p, d, frame,
                                                           color=colour):
                        break

    def _landmarks(self, ax, blocked, T, frame):
        fw, fh = frame
        size = 8.0
        chosen = []
        for lm in collect_landmarks(self.ds.osm, T.lonlat_bbox()):
            x, y = T.point(lm.point.x, lm.point.y)
            if 2 <= x <= fw - 2 and 2 <= y <= fh - 2:
                chosen.append((lm, x, y))
            if len(chosen) >= int(self.opt["landmarks"]):
                break
        for lm, x, y in chosen:
            ax.plot([x], [y], marker="*", ms=7.5, mfc=self.st["landmark"],
                    mec=self.st["landmark"], mew=0.4, ls="none", zorder=9)
            blocked.add((x - 1.6, y - 1.6, x + 1.6, y + 1.6))
        for lm, x, y in chosen:
            L = Label(lm.name, x, y, text_width_mm(lm.name, size, bold=True),
                      text_height_mm(size), True, size)
            if place_first_fit(L, frame, blocked, pad=0.35, max_ring=30.0):
                ax.text(L.tx, L.ty, L.text, ha=L.ha, va="center", fontsize=size,
                        fontweight="bold", fontfamily=font_family(),
                        color=self.st["landmark_text"], zorder=10)
