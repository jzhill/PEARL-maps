from shapely.geometry import Point, box

import pytest

from pearl_maps.geometry import PageTransform, Proj, nearest_north_up, split_bands


@pytest.mark.parametrize("deg, expected", [
    (0.0, 0.0), (36.6, 36.6), (-38.7, -38.7),          # already within 90 degrees: unchanged
    (159.4, -20.6), (-170.8, 9.2), (177.3, -2.7),      # the upside-down Teaoraereke / Bairiki / Taborio angles
    (90.0, 90.0), (-90.0, 90.0), (180.0, 0.0), (-180.0, 0.0), (270.0, 90.0),
])
def test_nearest_north_up_never_exceeds_90_degrees(deg, expected):
    got = nearest_north_up(deg)
    assert got == pytest.approx(expected)
    assert -90.0 < got <= 90.0


def test_projection_round_trip():
    pr = Proj(173.15, 1.35, deg=30.0)
    lon, lat = pr.inv(*pr.fwd(173.1512, 1.3521))
    assert abs(lon - 173.1512) < 1e-9 and abs(lat - 1.3521) < 1e-9


def test_one_degree_of_latitude_is_about_110_km():
    pr = Proj(173.0, 1.3)
    _, y = pr.fwd(173.0, 1.31)
    assert 1100 < y < 1110


def test_page_transform_point_matches_geometry_transform():
    T = PageTransform(Proj(173.15, 1.35, 12.0), 5.0, -3.0, 0.8, 194.0, 269.0)
    p = T(Point(173.1503, 1.3498))
    x, y = T.point(173.1503, 1.3498)
    assert abs(p.x - x) < 1e-9 and abs(p.y - y) < 1e-9


def test_split_bands_balance_households():
    # a 1 km x 100 m strip with households spread along it
    target = box(173.0, 1.30, 173.009, 1.3009)
    pts = [(173.0 + 0.009 * i / 99, 1.30045) for i in range(100)]
    bands = split_bands(target, pts, 2, overlap_m=0.0)
    counts = [sum(b.contains(Point(p)) for p in pts) for b in bands]
    assert len(bands) == 2
    assert abs(counts[0] - counts[1]) <= 2
