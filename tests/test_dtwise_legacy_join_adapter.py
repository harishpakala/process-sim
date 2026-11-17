"""Regression tests for legacy cross-domain discovery / Unified IR translation."""
from unittest.mock import patch
import pytest

from process_sim.dtwise.legacy_join_adapter import (
    _legacy_question, plan_legacy_projection_ir,
)


def test_revised_questions_preserve_explicit_roles():
    cases = [
        ("Get SignalName from OPCUAConnectivity for the DEXPI InstrumentationFunction "
         "with LocalID FI-001, matched through AssetIdentifier.",
         "Get SignalName of the DEXPI InstrumentationFunction with LocalID FI-001."),
        ("Find SignalName from OPCUAConnectivity associated with DEXPI "
         "InstrumentationFunctions through AssetIdentifier.",
         "Find SignalName associated with DEXPI InstrumentationFunctions through AssetIdentifier."),
        ("Get OPCUANodeId from OPCUAConnectivity for ECAD Devices matched through AssetIdentifier.",
         "Get OPCUANodeId for the ECAD Devices matched by AssetIdentifier."),
    ]
    for question, expected in cases:
        assert _legacy_question(question)[0] == expected


def test_legacy_join_never_approves_shared_identifiers_implicitly():
    discovered = {
        "source": {"domain": "dexpi", "key_predicate": "https://example.org/dexpi/hasAssetIdentifier"},
        "target": {"domain": "opcuaconnectivity",
                   "key_predicate": "https://example.org/opcuaconnectivity/hasAssetIdentifier"},
        "join_key_label": "AssetIdentifier",
    }
    with (patch("process_sim.dtwise.legacy_join_adapter.Schema"),
          patch("process_sim.dtwise.legacy_join_adapter._candidates", return_value=[]),
          patch("process_sim.dtwise.legacy_join_adapter.plan_cross_domain_projection",
                return_value=discovered)):
        with pytest.raises(ValueError, match="independently verified"):
            plan_legacy_projection_ir(
                "Find SignalName from OPCUAConnectivity associated with DEXPI "
                "InstrumentationFunctions through AssetIdentifier.",
                "schema.json", mappings=None)


def test_unrelated_single_domain_question_does_not_use_legacy_adapter():
    with (patch("process_sim.dtwise.legacy_join_adapter.Schema"),
          patch("process_sim.dtwise.legacy_join_adapter._candidates", return_value=[]),
          patch("process_sim.dtwise.legacy_join_adapter.plan_cross_domain_projection",
                return_value=None)):
        assert plan_legacy_projection_ir("Get SignalName from OPCUAConnectivity.",
                                         "schema.json", mappings=None) is None
