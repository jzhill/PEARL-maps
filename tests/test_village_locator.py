import pytest
from shapely.geometry import box

from pearl_maps.village_map import inflate_to_min


def test_tiny_extent_grows_to_the_minimum_about_its_centre():
    small = box(173.1000, 1.3600, 173.1010, 1.3606)
    out = inflate_to_min(small, 0.012)
    minx, miny, maxx, maxy = out.bounds
    assert max(maxx - minx, maxy - miny) == pytest.approx(0.012, abs=1e-9)
    assert out.centroid.x == pytest.approx(small.centroid.x, abs=1e-9)
    assert out.centroid.y == pytest.approx(small.centroid.y, abs=1e-9)


def test_extent_already_big_enough_is_untouched():
    big = box(173.10, 1.36, 173.13, 1.365)
    assert inflate_to_min(big, 0.012) is big
