import pytest
from selira.formal.identifier_comparison import identifier_matches

BASE = "https://aas.example.com/"


@pytest.mark.parametrize("local,asset,expected", [
    ("FI_101", "FI101", True),
    ("CV-1006", "CV1006", True),
    ("VC_105", "CV1006", False),
    ("TI_105", "TI1202", False),
    ("fi_101", "FI101", False),
    ("SC_101", "M1", False),
])
def test_normalized_matching(local, asset, expected):
    assert identifier_matches(local, BASE + asset) is expected


def test_explicit_exception():
    exceptions = {("SC_101", BASE + "M1")}
    assert identifier_matches("SC_101", BASE + "M1", exceptions=exceptions)
    assert not identifier_matches("SC_101", BASE + "M2", exceptions=exceptions)


@pytest.mark.parametrize("local,asset", [
    ("", BASE + "M1"), ("---", BASE + "M1"),
    ("M1", BASE), ("M1", "M1"), ("M1", BASE + "M1?x=1"),
])
def test_invalid_input(local, asset):
    with pytest.raises(ValueError):
        identifier_matches(local, asset)
