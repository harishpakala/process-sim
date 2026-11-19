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
