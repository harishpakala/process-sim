"""Conservative, auditable checks for two-function LLM comparison narratives.

Checks explicit evidence coverage, not semantic entailment or hallucination-free
reasoning. Fail closed when the answer is malformed or a claim is ambiguous.
"""
import math
import re


def _number_mentioned(text, value, *, percent=False):
    """Accept decimal representations at >=2 decimal places for percentages."""
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    pattern = r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\s*%?" if percent else r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
    for match in re.finditer(pattern, text):
        token = match.group(0)
        if percent and "%" not in token:
            continue
        try:
            number = float(token.strip().rstrip("%").strip())
        except ValueError:
            continue
        tolerance = max(0.005, abs(value) * 0.005) if percent else max(1e-6, abs(value) * 0.001)
        if abs(number - value) <= tolerance:
            return True
    return False


def validate_comparison_answer(answer, evidence):
    checks = {}
    if not isinstance(answer, dict) or not isinstance(answer.get("answer"), str) or not isinstance(answer.get("limitations"), list) or not all(isinstance(x, str) for x in answer["limitations"]):
        return {"status": "FAILED", "checks": {"valid_structure": False},
                "failed_checks": ["valid_structure"], "scope": "explicit_evidence_coverage_only"}
    narrative = answer["answer"]
    combined = narrative + " " + " ".join(answer["limitations"])
    lower = combined.lower()
    comparison = evidence["comparison"]
    series = comparison["series"]
    names = [s["engineering_function"] for s in series]
    checks["both_functions_named"] = all(re.search(r"\b" + re.escape(n) + r"\b", narrative, re.I) for n in names)
    checks["simulation_time_basis"] = "simulation" in lower and ("time" in lower or "second" in lower)
    checks["interval_endpoints"] = all(_number_mentioned(narrative, comparison[key]) for key in
        ("common_start_simulation_seconds", "common_end_simulation_seconds"))
    checks["endpoint_changes"] = all(_number_mentioned(narrative, s["endpoint_change"]) for s in series)
    checks["relative_changes"] = all(
        s["relative_endpoint_change_percent"] is not None and
        _number_mentioned(narrative, s["relative_endpoint_change_percent"], percent=True)
        for s in series
    ) if comparison["comparison_available"] else ("undefined" in lower or "unavailable" in lower)
    winner = comparison["larger_absolute_relative_change_index"]
    if winner in (0, 1):
        # Conservative attribution: winner must be the grammatical subject
        # of a simple comparative claim, rather than merely appearing somewhere.
        name = re.escape(names[winner])
        checks["correct_winner"] = bool(re.search(
            r"\b" + name + r"\b.{0,100}\b(?:changed more|larger|greater|higher|biggest|largest)\b",
            narrative, re.I | re.S))
    elif winner == "equal":
        checks["correct_winner"] = bool(re.search(r"\b(?:equal|same|tie)\b", narrative, re.I))
    else:
        checks["correct_winner"] = bool(re.search(r"\b(?:cannot|unavailable|undefined|insufficient)\b", narrative, re.I))
    checks["provisional_mapping"] = "provisional" in lower and "mapping" in lower
    checks["physical_binding_unverified"] = ("physical" in lower or "sensor" in lower) and (
        "not verified" in lower or "unverified" in lower)
    checks["shared_provenance_unverified"] = ("shared" in lower or "common" in lower) and (
        "provenance" in lower) and ("not verified" in lower or "unverified" in lower)
    checks["no_causal_claim"] = not bool(re.search(
        r"\b(?:caused|causes|causing|responsible for|due to)\b", narrative, re.I))
    failed = [name for name, passed in checks.items() if not passed]
    return {"status": "CHECKS_PASSED_LIMITED_SCOPE" if not failed else "FAILED",
            "checks": checks, "failed_checks": failed,
            "scope": "explicit_evidence_coverage_only",
            "limitations": ["String and numeric checks do not establish full semantic correctness.",
                            "Winner check recognizes only a limited set of comparative phrasings."]}
