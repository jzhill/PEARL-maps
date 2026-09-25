import csv

import pytest
from shapely.geometry import Point, Polygon

from pearl_maps.config import Config, Paths
from pearl_maps.data import load_landmarks, read_raw_landmarks, snap_to_land, write_landmarks
from pearl_maps.landmarks import Landmark, collect_landmarks

FIELDS = ["landmark_id", "name", "label", "category", "lon", "lat", "confidence"]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, FIELDS, restval="")
        w.writeheader()
        w.writerows(rows)


def row(i, name, category="school", confidence="high", label="", lon=173.1, lat=1.36):
    return dict(landmark_id=f"LM{i:03d}", name=name, label=label, category=category,
                lon=lon, lat=lat, confidence=confidence)


def make_cfg(tmp_path, min_confidence="medium"):
    paths = Paths(root=tmp_path, raw=tmp_path, processed=tmp_path, outputs=tmp_path, status=tmp_path)
    return Config(paths=paths, inputs={}, sources={}, scope={}, households={},
                  landmarks={"min_confidence": min_confidence,
                             "priority": {"school": 0, "church": 1, "gov": 2}},
                  ea_map={}, village_map={})


def test_read_accepts_valid_rows(tmp_path):
    p = tmp_path / "landmarks.csv"
    write_csv(p, [row(1, "Example Primary School"), row(2, "Example Church", "church", "medium"),
                  row(3, "Example Supermarket", "business", "medium")])
    rows = read_raw_landmarks(p)
    assert [r["name"] for r in rows] == ["Example Primary School", "Example Church", "Example Supermarket"]
    assert rows[0]["lon"] == 173.1 and rows[0]["lat"] == 1.36


def test_read_reports_every_problem_at_once(tmp_path):
    p = tmp_path / "landmarks.csv"
    write_csv(p, [
        row(1, "Bad Category", category="scool"),
        row(2, "Bad Confidence", confidence="sure"),
        row(3, "Swapped Coordinates", lon=1.36, lat=173.1),
        row(4, "First"), row(4, "Same Id"),
    ])
    with pytest.raises(ValueError) as e:
        read_raw_landmarks(p)
    msg = str(e.value)
    assert "category 'scool'" in msg
    assert "confidence 'sure'" in msg
    assert "swapped" in msg
    assert "duplicate landmark_id LM004" in msg


def test_read_rejects_missing_column(tmp_path):
    p = tmp_path / "landmarks.csv"
    p.write_text("landmark_id,name\nLM001,Example\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing column"):
        read_raw_landmarks(p)


def test_load_drops_low_confidence_and_orders_best_first(tmp_path):
    cfg = make_cfg(tmp_path, min_confidence="medium")
    write_csv(tmp_path / "landmarks.csv", [
        row(1, "Zed Office", "gov", "high"),
        row(2, "Doubtful Church", "church", "check"),
        row(3, "Medium Church", "church", "medium"),
        row(4, "High Church", "church", "high"),
        row(5, "Example School", "school", "medium"),
        row(6, "Ministry of Something Very Long (MOSVL)", "gov", "high", label="MOSVL"),
    ])
    write_landmarks(cfg, read_raw_landmarks(tmp_path / "landmarks.csv"))
    names = [lm.name for lm in load_landmarks(cfg)]
    assert "Doubtful Church" not in names
    assert names == ["Example School", "High Church", "Medium Church", "MOSVL", "Zed Office"]


def test_load_min_confidence_check_keeps_everything(tmp_path):
    cfg = make_cfg(tmp_path, min_confidence="check")
    write_csv(tmp_path / "landmarks.csv", [row(1, "Doubtful Church", "church", "check")])
    write_landmarks(cfg, read_raw_landmarks(tmp_path / "landmarks.csv"))
    assert [lm.name for lm in load_landmarks(cfg)] == ["Doubtful Church"]


class FakeOsm:
    """Stands in for the OSM GeoPackage: one square of land, about 1.1 km across."""
    def query(self, table, bbox):
        assert table == "land"
        return [(Polygon([(173.00, 1.30), (173.01, 1.30), (173.01, 1.31), (173.00, 1.31)]), {})]


def snap_row(name, lon, lat):
    return dict(name=name, lon=lon, lat=lat, notes="")


def test_snap_leaves_landmarks_on_land_alone():
    r = snap_row("On Land", 173.005, 1.305)
    assert snap_to_land([r], FakeOsm(), 200) == []
    assert (r["lon"], r["lat"]) == (173.005, 1.305)


def test_snap_moves_a_landmark_in_the_water_onto_land_and_says_so():
    r = snap_row("In Lagoon", 172.9995, 1.305)          # ~55 m west of the shore
    (row, moved), = snap_to_land([r], FakeOsm(), 200)
    assert row is r and 40 < moved < 70
    assert Polygon([(173.00, 1.30), (173.01, 1.30), (173.01, 1.31), (173.00, 1.31)]).contains(
        Point(r["lon"], r["lat"]))
    assert 173.00 < r["lon"] < 173.0002                 # a few metres in, not on the shoreline itself
    assert "onto land" in r["notes"]


def test_snap_reports_but_does_not_move_a_landmark_far_from_land():
    r = snap_row("Far Out", 172.97, 1.305)              # ~3 km west
    (row, moved), = snap_to_land([r], FakeOsm(), 200)
    assert moved is None and (r["lon"], r["lat"]) == (172.97, 1.305)


def test_collect_filters_bbox_and_long_names():
    def lm(name, x, y):
        return Landmark(name, "school", Point(x, y), 0, "high")
    lms = [lm("Inside", 173.10, 1.36), lm("Outside", 173.50, 1.36),
           lm("A" * 43, 173.10, 1.36), lm("Also Inside", 173.12, 1.37)]
    got = collect_landmarks(lms, (173.0, 1.3, 173.2, 1.4))
    assert [g.name for g in got] == ["Inside", "Also Inside"]


def test_collect_keeps_same_name_at_different_places_but_drops_duplicate_rows():
    def lm(name, x, y):
        return Landmark(name, "business", Point(x, y), 3, "medium")
    lms = [lm("Example Shop", 173.100, 1.360), lm("example shop", 173.10005, 1.36005),   # ~7 m: same place
           lm("Example Shop", 173.110, 1.360)]                                            # ~1 km: another branch
    got = collect_landmarks(lms, (173.0, 1.3, 173.2, 1.4))
    assert [(g.point.x) for g in got] == [173.100, 173.110]
