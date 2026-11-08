"""Evidence-only fallback for failed TEP NEXUS LLM answers.

Never patch arbitrary free-form LLM text: reconstruct a canonical answer
from known evidence and preserve the original separately for audit.
"""

# Created: 2026-11-02
# Author: Harish
from tep_nexus_answer_validation import validate_answer


def repair_answer(original_answer, evidence):
    """Return canonical answer plus validation; caller stores original separately."""
    latest = evidence["latest_persisted_observation"]
    function = evidence["engineering_function"]
    parts = [
        f"For engineering function {function}, the latest persisted measurement "
        f"is {latest['value']} at simulation time {latest['simulation_seconds']} seconds."
    ]
    if "associated_asset_uri" in evidence:
        parts.append(f"Associated asset: {evidence['associated_asset_uri']}.")
    stats = evidence.get("quantitative_temporal_analytics")
    if stats and stats.get("status") == "OK":
        parts.extend([
            f"Mean {stats['mean']}, standard deviation "
            f"{stats['standard_deviation_population']}.",
            f"Regression slope {stats['linear_regression_slope_per_simulation_minute']} "
            f"signal value per simulation minute; endpoint change "
            f"{stats['endpoint_change']}.",
            "These are descriptive simulation-time statistics, not a verified physical trend.",
        ])
    limitations = [
        "Engineering mapping is provisional.",
        "Shared run provenance is unverified.",
        "Physical sensor binding is not verified.",
        "The run identifier was supplied by an operator.",
    ]
    if float(latest["record_age_seconds"]) > 300:
        limitations.append(
            f"The latest persisted record is stale "
            f"({latest['record_age_seconds']} seconds old at query time)."
        )
    if stats and stats.get("history_truncated_by_limit"):
        limitations.append("History is truncated by the retrieval limit.")
    repaired = {"answer": " ".join(parts), "limitations": limitations}
    validation = validate_answer(repaired, evidence)
    return {
        "method": "deterministic_evidence_only_reconstruction",
        "original_answer": original_answer,
        "repaired_answer": repaired,
        "repaired_validation": validation,
        "repair_success": validation["status"] == "CHECKS_PASSED_LIMITED_SCOPE",
    }
