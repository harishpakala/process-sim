"""Two-stage research probe: numerical comparison separated from provenance interpretation.

The first LLM call sees only quantitative evidence. The second sees its
original numerical judgment plus provenance constraints. Both are checked
separately; no deterministic repair is applied.
"""

# Created: 2026-11-02
# Author: Harish
import math

def numerical_prompt():
    return ("Return ONLY JSON with exactly: engineering_functions (two IDs), "
            "relative_change_magnitudes_percent (two nonnegative numbers), "
            "larger_absolute_relative_change_function (one ID, 'equal', or null), "
            "numerical_conclusion (string). Compare ABSOLUTE percentage magnitudes. "
            "Negative signed changes have positive magnitudes. Do not discuss provenance.")

def interpretation_prompt():
    return ("Return ONLY JSON with exactly: numerical_conclusion (string), "
            "engineering_interpretation (string), limitations (array of strings), "
            "causal_inference_supported (boolean), physical_binding_verified (boolean), "
            "shared_run_provenance_verified (boolean). "
            "Do not alter the quantitative conclusion or claim physical causality. "
            "A provisional mapping does NOT make an available numerical comparison inconclusive. "
            "Mention provisional mapping, unverified physical sensor binding, "
            "unverified shared run provenance, and unsupported causal inference.")

def _close(a, b):
    return type(a) in (int, float) and math.isfinite(a) and math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-9)

def validate_numerical(answer, evidence):
    comp = evidence["comparison"]
    series = comp["series"]
    names = [s["engineering_function"] for s in series]
    index = comp["larger_absolute_relative_change_index"]
    winner = names[index] if type(index) is int else index
    keys = {"engineering_functions", "relative_change_magnitudes_percent",
            "larger_absolute_relative_change_function", "numerical_conclusion"}
    checks = {"schema": isinstance(answer, dict) and set(answer) == keys}
    if not checks["schema"]:
        return {"status": "FAILED", "checks": checks, "failed_checks": ["schema"]}
    values = answer["relative_change_magnitudes_percent"]
    expected = [s["relative_endpoint_change_percent"] for s in series]
    checks["functions"] = answer["engineering_functions"] == names
    checks["magnitudes"] = (isinstance(values, list) and len(values) == 2
                            and all(v is not None and _close(v, abs(e))
                                    for v, e in zip(values, expected) if e is not None)
                            and all(e is not None for e in expected))
    checks["winner"] = answer["larger_absolute_relative_change_function"] == winner
    conclusion = answer["numerical_conclusion"]
    checks["conclusion_consistent_with_evidence"] = (checks["winner"] and isinstance(conclusion, str)
        and bool(conclusion.strip()) and (winner in conclusion if isinstance(winner, str)
                                         else "unavailable" in conclusion.lower()))
    failed = [k for k, ok in checks.items() if not ok]
    return {"status": "CHECKS_PASSED_LIMITED_SCOPE" if not failed else "FAILED",
            "checks": checks, "failed_checks": failed}

def validate_interpretation(answer, numerical, evidence):
    keys = {"numerical_conclusion", "engineering_interpretation", "limitations",
            "causal_inference_supported", "physical_binding_verified",
            "shared_run_provenance_verified"}
    checks = {"schema": isinstance(answer, dict) and set(answer) == keys}
    if not checks["schema"]:
        return {"status": "FAILED", "checks": checks, "failed_checks": ["schema"]}
    winner_index = evidence["comparison"]["larger_absolute_relative_change_index"]
    names = [s["engineering_function"] for s in evidence["comparison"]["series"]]
    winner = names[winner_index] if type(winner_index) is int else winner_index
    conclusion = answer["numerical_conclusion"]
    checks["numerical_conclusion_retained"] = (isinstance(conclusion, str) and
        conclusion == numerical.get("numerical_conclusion") and
        (winner in conclusion if isinstance(winner, str) else "unavailable" in conclusion.lower()))
    checks["engineering_interpretation_present"] = isinstance(answer["engineering_interpretation"], str) and bool(answer["engineering_interpretation"].strip())
    checks["provenance_flags"] = (answer["causal_inference_supported"] is False and
        answer["physical_binding_verified"] is False and
        answer["shared_run_provenance_verified"] is False)
    limits = answer["limitations"]
    lower = " ".join(limits).lower() if isinstance(limits, list) and all(isinstance(x, str) for x in limits) else ""
    checks["limitations"] = (all(word in lower for word in ("provisional", "mapping", "provenance"))
        and ("physical" in lower or "sensor" in lower)
        and ("unverified" in lower or "not verified" in lower)
        and ("causal" in lower or "causation" in lower))
    failed = [k for k, ok in checks.items() if not ok]
    return {"status": "CHECKS_PASSED_LIMITED_SCOPE" if not failed else "FAILED",
            "checks": checks, "failed_checks": failed,
            "scope": "field_and_keyword_checks_not_semantic_entailment"}
