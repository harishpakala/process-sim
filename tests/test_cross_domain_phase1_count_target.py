"""Cross-domain COUNT target grounding regressions."""
from process_sim.dtwise.shacl_planner.cross_domain_phase1 import _explicit_count_target_ids


CANDIDATES = [
    {"id": "ecad:R2", "domain": "ecad", "kind": "result", "path": "ECAD → Device"},
    {"id": "dexpi:R3", "domain": "dexpi", "kind": "result", "path": "DEXPI → Equipment"},
]


def test_count_ecad_device_not_matching_equipment():
    assert _explicit_count_target_ids(
        "Count ECAD Device with matching DEXPI Equipment using AssetIdentifier.",
        CANDIDATES,
    ) == {"ecad:R2"}


def test_count_dexpi_equipment():
    assert _explicit_count_target_ids(
        "How many DEXPI Equipment match ECAD Device?", CANDIDATES,
    ) == {"dexpi:R3"}


def test_count_without_exact_owner_is_not_inferred():
    assert _explicit_count_target_ids(
        "Count matching cross-domain records.", CANDIDATES,
    ) == set()
