from pearl_maps.plan import StatusRow, parse_map_filename, sync_status_from_maps


def test_parse_single_ea():
    assert parse_map_filename("70502220_enumeration_map_260920.pdf") == (["70502220"], "260920")


def test_parse_split_suffix_and_short_ids():
    assert parse_map_filename("71506320-6310a_ea_map_250915.pdf") == (
        ["71506320", "71506310"], "250915")
    assert parse_map_filename("71105010-04920_enumeration_map_260324.pdf") == (
        ["71105010", "71104920"], "260324")
    assert parse_map_filename("71608220-8211-8212_enumeration_map_250203.pdf")[0] == [
        "71608220", "71608211", "71608212"]


def test_parse_ignores_other_files():
    assert parse_map_filename("bikenibeu_orientation_map_260920.pdf") is None
    assert parse_map_filename("_build_log.csv") is None


def test_sync_marks_mapped_but_never_touches_blocked():
    status = {
        "70502220": StatusRow("70502220", "Bikenibeu", "pending"),
        "61401401": StatusRow("61401401", "Buota", "blocked", note="no listing"),
    }
    files = ["70502220_enumeration_map_260920.pdf", "61401401_enumeration_map_260920.pdf"]
    sync_status_from_maps(status, files, {"70502220": "Bikenibeu", "61401401": "Buota"})
    assert status["70502220"].status == "mapped"
    assert status["70502220"].map_date == "2026-09-20"
    assert status["61401401"].status == "blocked"
