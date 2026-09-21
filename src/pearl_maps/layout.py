"""Page geometry and the choice of orientation / rotation for an EA page."""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry

from .geometry import PageTransform, Proj, long_axis_deg

A4_PORTRAIT = (210.0, 297.0)
A4_LANDSCAPE = (297.0, 210.0)
MARGIN = dict(left=8.0, right=8.0, top=16.0, bottom=12.0)   # mm; top holds the title


def frame_rect(page: tuple[float, float]) -> tuple[float, float, float, float]:
    """(x, y, w, h) of the map frame on the page, in mm."""
    w, h = page
    return (MARGIN["left"], MARGIN["bottom"],
            w - MARGIN["left"] - MARGIN["right"], h - MARGIN["top"] - MARGIN["bottom"])


@dataclass(frozen=True)
class Layout:
    page: tuple[float, float]
    transform: PageTransform

    @property
    def rotation(self) -> float:
        return self.transform.proj.deg

    @property
    def orientation(self) -> str:
        return "portrait" if self.page[0] < self.page[1] else "landscape"


def _candidate_angles(target_ll: BaseGeometry) -> list[float]:
    """Angles that put the target's long axis along a page edge."""
    c = target_ll.centroid
    a = long_axis_deg(Proj(c.x, c.y).geom(target_ll))
    out = []
    for cand in (-a, -a + 90.0):
        cand = (cand + 180.0) % 180.0
        if cand > 90.0:
            cand -= 180.0
        if abs(cand) > 1.0:
            out.append(cand)
    return out


def _best(target_ll: BaseGeometry, angles: list[float], pad_m: float,
          rotation_penalty: float) -> Layout:
    c = target_ll.centroid
    best = None
    for page in (A4_PORTRAIT, A4_LANDSCAPE):
        _, _, fw, fh = frame_rect(page)
        for deg in angles:
            pr = Proj(c.x, c.y, deg)
            minx, miny, maxx, maxy = pr.geom(target_ll).bounds
            mm_per_m = min(fw / (maxx - minx + 2 * pad_m), fh / (maxy - miny + 2 * pad_m))
            score = mm_per_m / (rotation_penalty if abs(deg) > 1e-6 else 1.0)
            if best is None or score > best[0]:
                t = PageTransform(pr, (minx + maxx) / 2, (miny + maxy) / 2, mm_per_m, fw, fh)
                best = (score, Layout(page, t))
    return best[1]


def layout_options(target_ll: BaseGeometry, north_up_preference: float = 1.18,
                   pad_m: float = 12.0) -> list[Layout]:
    """Layouts to try, in order: best north-up; best overall (a rotation must
    beat north-up by ``north_up_preference``); best rotated regardless."""
    rot = _candidate_angles(target_ll)
    tries = [
        _best(target_ll, [0.0], pad_m, 1.0),
        _best(target_ll, [0.0, *rot], pad_m, north_up_preference),
    ]
    if rot:
        tries.append(_best(target_ll, rot, pad_m, 1.0))
    out: list[Layout] = []
    for lay in tries:
        if not any(abs(o.rotation - lay.rotation) < 0.5 and o.page == lay.page for o in out):
            out.append(lay)
    return out


def nice_scalebar_m(mm_per_m: float, frame_w: float) -> int:
    target = frame_w * 0.22 / mm_per_m
    for v in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000):
        if v >= target:
            return v
    return 2000
