import random

from shapely.geometry import box

from pearl_maps.labels import Grid, Label, overlaps, place_labels, text_width_mm


def test_grid_detects_overlap_only_when_boxes_intersect():
    g = Grid()
    g.add((0, 0, 10, 5))
    assert g.hits((9, 4, 12, 8))
    assert not g.hits((10.5, 0, 12, 5))


def test_text_width_scales_with_font_size():
    assert text_width_mm("Head One", 10) > text_width_mm("Head One", 8)


def _cluster(n=25, seed=1, spread=20):
    rnd = random.Random(seed)
    labs = []
    for i in range(n):
        x, y = 60 + rnd.uniform(-spread, spread), 60 + rnd.uniform(-spread, spread)
        t = f"Household head {i}"
        labs.append(Label(t, x, y, text_width_mm(t, 10), 3.4, True, 10))
    return labs


def test_placed_labels_never_overlap_each_other_or_markers():
    labs = _cluster()
    markers = Grid()
    for L in labs:
        markers.add((L.x - 0.75, L.y - 0.75, L.x + 0.75, L.y + 0.75))
    place_labels(labs, (200, 200), markers)
    placed = [L.placed for L in labs if L.placed]
    assert len(placed) == len(labs)        # this density fits comfortably
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            assert not overlaps(a, b)
        for L in labs:
            m = (L.x - 0.75, L.y - 0.75, L.x + 0.75, L.y + 0.75)
            assert not overlaps(a, m)


def test_focus_labels_stay_inside_allowed_region():
    labs = _cluster(15)
    allowed = box(20, 20, 110, 110)
    place_labels(labs, (200, 200), Grid(), allowed_focus=allowed)
    for L in labs:
        if L.placed:
            assert allowed.contains(box(*L.placed))
