"""Check structured LLM comparison reports against deterministic evidence."""
import math

def structured_prompt():
    return ("Return only a JSON object with exactly: engineering_functions (two IDs), "
            "simulation_interval_seconds (two numbers), aligned_sample_count (integer), "
            "measurements (two objects with engineering_function, endpoint_change, "
            "relative_endpoint_change_percent), larger_absolute_relative_change_function "
            "(ID, 'equal', or null), conclusion (string), limitations (array of strings). "
            "Use the exact numerical evidence supplied. Include both functions and the "
            "winner in the conclusion. Limitations must mention provisional engineering "
            "mapping, unverified physical sensor binding, unverified shared run provenance, "
            "and unsupported causal inference. Do not invent values or causality.")

def validate_structured_answer(answer, evidence):
    required = {"engineering_functions", "simulation_interval_seconds",
                "aligned_sample_count", "measurements",
                "larger_absolute_relative_change_function", "conclusion", "limitations"}
    checks = {"schema": isinstance(answer, dict) and set(answer) == required}
    if not checks["schema"]:
        return {"status": "FAILED", "checks": checks, "failed_checks": ["schema"],
                "scope": "structured_field_checks_only"}
    comp = evidence["comparison"]
    series = comp["series"]
    names = [s["engineering_function"] for s in series]
    def same(a, b):
        if b is None:
            return a is None
        return type(a) in (int, float) and math.isfinite(a) and math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-9)
    checks["functions"] = answer["engineering_functions"] == names
    interval = answer["simulation_interval_seconds"]
    checks["interval"] = (isinstance(interval, list) and len(interval) == 2
                          and same(interval[0], comp["common_start_simulation_seconds"])
                          and same(interval[1], comp["common_end_simulation_seconds"]))
    checks["sample_count"] = (type(answer["aligned_sample_count"]) is int
                              and answer["aligned_sample_count"] == comp["common_sample_count"])
    measures = answer["measurements"]
    checks["measurements"] = (isinstance(measures, list) and len(measures) == 2
        and all(isinstance(g, dict)
                and set(g) == {"engineering_function", "endpoint_change", "relative_endpoint_change_percent"}
                and g["engineering_function"] == s["engineering_function"]
                and same(g["endpoint_change"], s["endpoint_change"])
                and same(g["relative_endpoint_change_percent"], s["relative_endpoint_change_percent"])
                for g, s in zip(measures, series)))
    winner_index = comp["larger_absolute_relative_change_index"]
    winner = names[winner_index] if type(winner_index) is int else winner_index
    checks["winner"] = answer["larger_absolute_relative_change_function"] == winner
    conclusion = answer["conclusion"]
    checks["conclusion"] = (isinstance(conclusion, str) and bool(conclusion.strip())
                            and (winner in conclusion if isinstance(winner, str)
                                 else "unavailable" in conclusion.lower()))
    limitations = answer["limitations"]
    lower = (" ".join(limitations).lower() if isinstance(limitations, list)
             and all(isinstance(x, str) for x in limitations) else "")
    checks["limitations"] = (all(x in lower for x in ("provisional", "mapping", "provenance"))
        and ("physical" in lower or "sensor" in lower)
        and ("not verified" in lower or "unverified" in lower)
        and ("causal" in lower or "causation" in lower))
    checks["no_explicit_causality"] = (isinstance(conclusion, str) and not any(
        x in conclusion.lower() for x in ("caused", "causes", "due to", "responsible for")))
    failed = [k for k, v in checks.items() if not v]
    return {"status": "CHECKS_PASSED_LIMITED_SCOPE" if not failed else "FAILED",
            "checks": checks, "failed_checks": failed,
            "scope": "structured_field_checks_only",
            "limitations": ["Free-text semantic entailment is not verified.",
                            "Limitations are checked by keyword coverage."]}
