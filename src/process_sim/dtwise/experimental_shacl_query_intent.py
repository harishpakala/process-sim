"""Phase 5.4: schema-verified structured intent for the ECAD two-filter join.

An additive representation of a validated planner selection, not a new
source of truth. Never compile a model-supplied intent without validation.
"""
from process_sim.dtwise.experimental_shacl_phase4_join import _expected_paths
from process_sim.dtwise.experimental_shacl_phase4_and_join import (
    _filter_ids, _literals, validate_phase4_and_join_plan,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def validated_join_intent(plan, qualified):
    """Build a structured intent only from independently verified selections."""
    verified = validate_phase4_and_join_plan(plan, qualified)
    if verified["status"] != "selected":
        raise SelectionContractError("Cannot build intent from unresolved selection")
    domain = qualified["prompt"]["domain"]
    if domain != "ecad":
        raise SelectionContractError("Unsupported structured join domain")
    values = _literals(qualified["prompt"]["question"])
    if values is None or tuple(f["value"] for f in verified["filters"]) != values:
        raise SelectionContractError("Intent filter literals contradict question")
    expected = _expected_paths(qualified)
    filters = _filter_ids(qualified)
    return {
        "domain": domain,
        "operation": "select",
        "result_property_ids": list(expected),
        "join": {"kind": "shared_ancestor", "owner": "Device"},
        "boolean_operator": "and",
        "filters": [
            {"property_id": fid, "owner": "Device", "property": name,
             "operator": "=", "value": value}
            for fid, name, value in zip(filters, ("LocalId", "DeviceType"), values)
        ],
    }
