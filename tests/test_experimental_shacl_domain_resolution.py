"""Offline Phase 5.1 domain-resolution tests."""
import pytest

from process_sim.dtwise.experimental_shacl_domain_resolution import (
    DomainResolutionError, resolve_domain,
)

DOMAINS = {"dexpi", "ecad"}


@pytest.mark.parametrize("question, expected", [
    ("Show Address in ECAD", "ecad"),
    ("Show InstrumentationFunction in DEXPI", "dexpi"),
    ("In ecad, show EndPoint Address", "ecad"),
    ("Show EndPoint Address in ECAD.", "ecad"),
])
def test_explicit_domain(question, expected):
    assert resolve_domain(question, DOMAINS) == expected


def test_explicit_override_without_mention():
    assert resolve_domain("Show Address", DOMAINS, override="ECAD") == "ecad"


def test_matching_override():
    assert resolve_domain("Show Address in ECAD", DOMAINS, override="ecad") == "ecad"


def test_conflicting_override():
    with pytest.raises(DomainResolutionError, match="conflicts"):
        resolve_domain("Show Address in ECAD", DOMAINS, override="dexpi")


def test_multiple_domains_ambiguous():
    with pytest.raises(DomainResolutionError, match="Ambiguous"):
        resolve_domain("Compare ECAD and DEXPI", DOMAINS)


def test_no_domain_unresolved():
    with pytest.raises(DomainResolutionError, match="unresolved"):
        resolve_domain("Show Address", DOMAINS)


def test_unknown_override():
    with pytest.raises(DomainResolutionError, match="Unknown"):
        resolve_domain("Show Address", DOMAINS, override="other")


def test_no_substring_false_positive():
    with pytest.raises(DomainResolutionError, match="unresolved"):
        resolve_domain("Show myecadvalue", DOMAINS)


def test_missing_index_domains():
    with pytest.raises(DomainResolutionError, match="No schema domains"):
        resolve_domain("Show Address in ECAD", set())


# Phase 5.2: deterministic evidence from indexed SHACL NodeShape labels.
SHAPE = "http://www.w3.org/ns/shacl#NodeShape"
SCHEMA = {"concepts": [
    {"domain": "ecad", "types": [SHAPE], "labels": ["EndPoint"]},
    {"domain": "ecad", "types": [SHAPE], "labels": ["PLCEndPoint"]},
    {"domain": "ecad", "types": [SHAPE], "labels": ["Device"]},
    {"domain": "dexpi", "types": [SHAPE], "labels": ["InstrumentationFunction"]},
    {"domain": "dexpi", "types": [SHAPE], "labels": ["Device"]},
    {"domain": "ecad", "types": [], "labels": ["Address"]},
]}


def test_unnamed_ecad_inferred_from_unique_shapes():
    assert resolve_domain(
        "Show EndPoint Address and PLCEndPoint Address belonging to the same Device",
        DOMAINS, schema=SCHEMA) == "ecad"


def test_unnamed_dexpi_inferred_from_shape():
    assert resolve_domain(
        "Show InstrumentationFunction", DOMAINS, schema=SCHEMA) == "dexpi"


def test_shared_shape_is_ambiguous():
    with pytest.raises(DomainResolutionError, match="Ambiguous"):
        resolve_domain("Show Device", DOMAINS, schema=SCHEMA)


def test_cross_domain_shape_mentions_ambiguous():
    with pytest.raises(DomainResolutionError, match="Ambiguous"):
        resolve_domain("Show EndPoint and InstrumentationFunction", DOMAINS, schema=SCHEMA)


def test_generic_property_without_shape_unresolved():
    with pytest.raises(DomainResolutionError, match="unresolved"):
        resolve_domain("Show Address", DOMAINS, schema=SCHEMA)


def test_explicit_domain_precedes_shape_evidence():
    assert resolve_domain(
        "Show InstrumentationFunction in ECAD", DOMAINS, schema=SCHEMA) == "ecad"


def test_override_precedes_shape_evidence():
    assert resolve_domain(
        "Show EndPoint", DOMAINS, override="dexpi", schema=SCHEMA) == "dexpi"


def test_partial_shape_name_not_matched():
    with pytest.raises(DomainResolutionError, match="unresolved"):
        resolve_domain("Show SuperEndPointValue", DOMAINS, schema=SCHEMA)


# Phase 5.2 integration guard: Phase 4.3 accepts the already-resolved
# domain while retaining exact two-filter question grounding.
from process_sim.dtwise.experimental_shacl_phase4_and_join import _literals


def test_phase43_without_redundant_domain_suffix():
    question = ("Show EndPoint Address and PLCEndPoint Address belonging to "
                "the same Device where Device LocalId = FI_101 and "
                "Device DeviceType = Sensor")
    assert _literals(question) == ("FI_101", "Sensor")
    assert _literals(question + " in ECAD") == ("FI_101", "Sensor")


def test_phase43_rejects_missing_or_changed_filter():
    base = ("Show EndPoint Address and PLCEndPoint Address belonging to "
            "the same Device where Device LocalId = FI_101")
    assert _literals(base) is None
    assert _literals(base + " and Device DeviceType != Sensor") is None
    assert _literals(base + " and Device DeviceType = Sensor in DEXPI") is None
