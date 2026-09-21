"""Text measurement and non-overlapping label placement.

Everything is in page millimetres. A label is an axis-aligned box that must
not overlap another label, must not cover any marker, and (optionally) must
lie inside an *allowed* region and outside a *forbidden* one.

Placement: every label gets a list of candidate boxes on expanding rings
around its anchor, cheapest (closest, to the right) first. Labels are then
seated greedily, most-constrained first, and a repair pass evicts and re-seats
a single blocker when that frees a stuck label. No leader lines are drawn;
labels simply drift away from their marker when space is tight.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely.geometry import box
from shapely.prepared import prep

PT_MM = 25.4 / 72.0

# ---------------------------------------------------------------- fonts

_font = {"family": "DejaVu Sans", "prop": FontProperties(family="DejaVu Sans")}
_width_cache: dict[tuple[str, float, bool], float] = {}


def use_font(candidates: list[str]) -> str:
    """Select the first installed font from ``candidates``. Arial and Liberation
    Sans share metrics, so maps lay out the same on Windows and Linux."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            _font["family"] = name
            _font["prop"] = FontProperties(family=name)
            _width_cache.clear()
            return name
    return _font["family"]


def font_family() -> str:
    return _font["family"]


def text_width_mm(s: str, size_pt: float, bold: bool = False) -> float:
    key = (s, round(size_pt, 2), bold)
    if key not in _width_cache:
        prop = _font["prop"].copy()
        if bold:
            prop.set_weight("bold")
        w = TextPath((0, 0), s, size=size_pt, prop=prop).get_extents().width
        _width_cache[key] = (w if w > 0 else 0.5 * size_pt * len(s)) * PT_MM
    return _width_cache[key]


def text_height_mm(size_pt: float) -> float:
    return size_pt * PT_MM * 0.95


# ---------------------------------------------------------------- spatial index

Box = tuple[float, float, float, float]


def overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Grid:
    """Uniform-grid index of occupied boxes (labels, markers, reserved areas)."""

    def __init__(self, cell: float = 6.0):
        self.cell = cell
        self._g: dict[tuple[int, int], list[Box]] = {}

    def _keys(self, b: Box):
        c = self.cell
        for i in range(int(b[0] // c), int(b[2] // c) + 1):
            for j in range(int(b[1] // c), int(b[3] // c) + 1):
                yield i, j

    def add(self, b: Box) -> None:
        for k in self._keys(b):
            self._g.setdefault(k, []).append(b)

    def hits(self, b: Box) -> bool:
        return any(overlaps(b, o) for k in self._keys(b) for o in self._g.get(k, ()))


# ---------------------------------------------------------------- candidates

RINGS_MM = (0.9, 1.6, 2.5, 3.6, 5.0, 6.8, 9.0, 11.5, 14.5, 18.0, 22.0, 26.0, 30.0)
ANGLES = tuple(i * 22.5 for i in range(16))
# right of the marker reads best, then left, then above/below
ANGLE_COST = {0.0: 0.0, 22.5: 0.15, 337.5: 0.25, 45.0: 0.45, 315.0: 0.55,
              180.0: 0.30, 157.5: 0.45, 202.5: 0.55, 90.0: 0.7, 270.0: 0.8}


@dataclass
class Label:
    text: str
    x: float                  # anchor (marker) position, mm
    y: float
    w: float                  # text box size, mm
    h: float
    focus: bool = True        # focus labels are seated first and may drift further
    size_pt: float = 10.0
    placed: Box | None = None
    ha: str = "left"
    tx: float = 0.0           # text draw position
    ty: float = 0.0
    candidates: list = field(default_factory=list, repr=False)

    def seat(self, cand) -> None:
        _, self.placed, self.ha, self.tx, self.ty = cand


def candidates(lab: Label, frame: tuple[float, float], blocked: Grid, pad: float,
               max_ring: float, allowed=None, forbidden=None) -> list:
    """Candidate positions (cost, box, ha, tx, ty), cheapest first.
    ``allowed`` / ``forbidden`` are prepared shapely geometries or None."""
    fw, fh = frame
    out = []
    for r in RINGS_MM:
        if r > max_ring:
            break
        for a in ANGLES:
            ar = math.radians(a)
            ox, oy = lab.x + r * math.cos(ar), lab.y + r * math.sin(ar)
            ca = math.cos(ar)
            if ca > 0.35:
                ha, x0 = "left", ox
            elif ca < -0.35:
                ha, x0 = "right", ox - lab.w
            else:
                ha, x0 = "center", ox - lab.w / 2
            y0 = oy - lab.h / 2
            b = (x0 - pad, y0 - pad, x0 + lab.w + pad, y0 + lab.h + pad)
            if b[0] < 0.4 or b[1] < 0.4 or b[2] > fw - 0.4 or b[3] > fh - 0.4:
                continue
            if blocked.hits(b):
                continue
            if allowed is not None or forbidden is not None:
                sb = box(*b)
                if allowed is not None and not allowed.contains(sb):
                    continue
                if forbidden is not None and forbidden.intersects(sb):
                    continue
            tx = {"left": x0, "right": x0 + lab.w, "center": x0 + lab.w / 2}[ha]
            out.append((r + ANGLE_COST.get(a, 0.9) * 1.2, b, ha, tx, oy))
    out.sort(key=lambda t: t[0])
    return out


def place_first_fit(lab: Label, frame, blocked: Grid, pad=0.4, max_ring=9.0,
                    allowed=None) -> bool:
    """Seat one label at its cheapest free position and block that space.
    Used for landmarks and EA numbers, which are placed before household names."""
    for cand in candidates(lab, frame, blocked, pad, max_ring,
                           prep(allowed) if allowed is not None else None):
        lab.seat(cand)
        blocked.add(lab.placed)
        return True
    return False


# ---------------------------------------------------------------- placement

def place_labels(labels: list[Label], frame: tuple[float, float], blocked: Grid,
                 allowed_focus=None, forbidden_neighbour=None, pad: float = 0.45,
                 max_ring_focus: float = 28.0, max_ring_neighbour: float = 12.0) -> None:
    """Seat labels without overlap. Focus labels must stay inside
    ``allowed_focus``; neighbour labels must stay out of ``forbidden_neighbour``."""
    pa = prep(allowed_focus) if allowed_focus is not None else None
    pf = prep(forbidden_neighbour) if forbidden_neighbour is not None else None
    for L in labels:
        L.placed = None
        L.candidates = candidates(
            L, frame, blocked, pad,
            max_ring_focus if L.focus else min(max_ring_neighbour, max_ring_focus),
            allowed=pa if L.focus else None,
            forbidden=None if L.focus else pf)

    order = sorted(range(len(labels)),
                   key=lambda i: (not labels[i].focus, len(labels[i].candidates)))
    grid = Grid()
    for i in order:
        for cand in labels[i].candidates:
            if not grid.hits(cand[1]):
                labels[i].seat(cand)
                grid.add(cand[1])
                break

    # repair: free a stuck focus label by moving exactly one blocker elsewhere
    for _ in range(3):
        stuck = [i for i in order if labels[i].placed is None and labels[i].focus]
        if not stuck:
            return
        progress = False
        for i in stuck:
            L = labels[i]
            for cand in L.candidates[:60]:
                blockers = [j for j, o in enumerate(labels)
                            if o.placed and overlaps(o.placed, cand[1])]
                if len(blockers) != 1:
                    continue
                B = labels[blockers[0]]
                if B.focus and len(B.candidates) < len(L.candidates):
                    continue                      # B is harder to place than L
                old = (0, B.placed, B.ha, B.tx, B.ty)
                B.placed = None
                L.seat(cand)
                grid = _grid_of(labels)
                for c2 in B.candidates:
                    if not grid.hits(c2[1]):
                        B.seat(c2)
                        grid.add(c2[1])
                        break
                if B.placed is None and B.focus:  # undo: keep the stronger claim
                    B.seat(old)
                    L.placed = None
                    grid = _grid_of(labels)
                    continue
                progress = True
                break
        if not progress:
            return


def _grid_of(labels: list[Label]) -> Grid:
    g = Grid()
    for L in labels:
        if L.placed:
            g.add(L.placed)
    return g
