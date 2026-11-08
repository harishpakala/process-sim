"""Regression checks for structural correspondence without trust promotion."""
from process_sim.selira.functional_paths import assess_functional_paths, resolve_functional_paths


def row(function="PI_101", signal="XMEAS7", address="I10.19",
        device="PI-1101", status="PROVISIONAL_ENGINEERING_MATCH"):
    return dict(dexpiId=function, signal=signal, plcAddress=address,
                ecadId=device, mappingStatus=status,
                dexpiGraph="urn:dexpi", opcuaGraph="urn:opcua",
                inventoryGraph="urn:inventory", ecadGraph="urn:ecad")


def test_three_complete_provisional_paths():
    paths = [row(), row("PI_102", "XMEAS13", "I10.20", "PI-1301"),
             row("PI_103", "XMEAS16", "I10.18", "PI-1501")]
    result = assess_functional_paths(paths, ["PI_101", "PI_102", "PI_103"])
    assert all(value["status"] == "structurally_supported_provisional"
               for value in result.values())
    assert all(not value["consumer_authorized"] for value in result.values())
    assert all(value["operational_binding"] == "unverified"
               for value in result.values())


def test_missing_path_is_unresolved():
    result = assess_functional_paths([], ["PI_101"])
    assert result["PI_101"]["status"] == "unresolved"


def test_competing_device_is_ambiguous():
    result = assess_functional_paths([row(), row(device="PI-9999")], ["PI_101"])
    assert result["PI_101"]["status"] == "ambiguous"


def test_conflicting_status_is_ambiguous():
    result = assess_functional_paths([row(), row(status="VERIFIED")], ["PI_101"])
    assert result["PI_101"]["status"] == "ambiguous"


def test_unknown_status_does_not_grant_authorization():
    result = assess_functional_paths([row(status="VERIFIED")], ["PI_101"])
    assert result["PI_101"]["status"] == "unverified_mapping_status"
    assert not result["PI_101"]["consumer_authorized"]


def test_injected_reader():
    result = resolve_functional_paths(["PI_101"], reader=lambda **kwargs: [row()])
    assert result["PI_101"]["status"] == "structurally_supported_provisional"
