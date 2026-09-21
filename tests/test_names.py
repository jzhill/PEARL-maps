"""Name cleaning. All names here are synthetic placeholders - never use real
household-head names from the listing in tests."""
import pytest

from pearl_maps.data import clean_head_name


@pytest.mark.parametrize("raw, expected", [
    ("Head One", "Head One"),
    ("Head.Two", "Head. Two"),                        # missing space after full stop
    ("Head .Three", "Head. Three"),                   # space on the wrong side
    ("  Head   Four ", "Head Four"),                  # stray whitespace
    ("Head Five (note added by enumerator)", "Head Five"),   # trailing note dropped
    ("##N/A##", None),                                # placeholder -> marker only
    (".a", None),
    ("", None),
    (None, None),
])
def test_clean_head_name(raw, expected):
    assert clean_head_name(raw) == expected


def test_long_names_are_truncated_with_ellipsis():
    out = clean_head_name("Head Six With A Very Long Synthetic Name", max_chars=30)
    assert len(out) == 30
    assert out.endswith("…")
