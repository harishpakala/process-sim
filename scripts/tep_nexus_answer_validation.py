"""Conservative, deterministic checks for TEP NEXUS generated answers.

This is NOT open-ended factual verification. It checks selected explicit
claims and required caveats against retrieved evidence; unparsed claims
are outside scope. Failed checks do not prevent evidence preservation.
"""
import math
import re


def _number_after(text, label):
    pattern = r"\b" + label + r"\s*(?:of|is|:|=)?\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    match = re.search(pattern, text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _matches(actual, expected):
    return math.isfinite(actual) and math.isclose(
        actual, float(expected), rel_tol=1e-6, abs_tol=1e-8
    )


def validate_answer(answer, evidence, stale_after_seconds=300):
    """Check explicit numeric fields and critical semantic/provenance caveats.

    Return a structured limited-scope result; do not treat it as proof
    that all free-form statements are correct.
    """
    if not isinstance(answer, dict) or not isinstance(answer.get("answer"), str):
        raise ValueError("Answer must contain an answer string")
    limitations = answer.get("limitations", [])
    if not isinstance(limitations, list) or not all(isinstance(x, str) for x in limitations):
        raise ValueError("Limitations must be a list of strings")
    text = answer["answer"]
    combined = text + " " + " ".join(limitations)
    checks = []

    def check(name, passed, detail):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    function = evidence["engineering_function"]
    check("function_identifier", bool(re.search(r"\b" + re.escape(function) + r"\b", text)), "Engineering function must be named")
    latest = evidence["latest_persisted_observation"]
    observed = _number_after(text, r"(?:latest (?:persisted )?measurement|latest (?:persisted )?value)")
    check("latest_value", observed is not None and _matches(observed, latest["value"]), "Latest value must be explicitly stated and match evidence")
    check("provisional_mapping", bool(re.search(r"(?:mapping|engineering correspondence)[^.\n;]{0,100}provisional|provisional[^.\n;]{0,70}(?:mapping|engineering correspondence)", combined, re.I)), "Mapping must be described as provisional")
    check("shared_run_provenance", bool(re.search(r"(?:shared run provenance|run provenance)[^.\n;]{0,80}(?:unverified|not verified)|(?:unverified|not verified)[^.\n;]{0,80}(?:shared run provenance|run provenance)", combined, re.I)), "Shared run provenance must be unverified")
    check("no_physical_verification_claim", not bool(re.search(r"\b(?:physically verified|verified physical sensor|approved sensor mapping)\b", combined, re.I)), "No physical verification claim")
    check("no_trend_mapping_conflation", not bool(re.search(r"\btrend\b[^.\n;]{0,70}\bprovisional\b|\bprovisional\s+trend\b", combined, re.I)), "Do not call statistical trend provisional because mapping is provisional")
    age = float(latest["record_age_seconds"])
    if age > stale_after_seconds:
        check("stale_record_disclosure", bool(re.search(r"\b(?:stale|old|outdated|not fresh|not live|hours? old|minutes? old)\b", combined, re.I)), "Old persisted data must be disclosed as stale")
    check("no_unqualified_live_claim", not bool(re.search(r"\b(?:live|real.time|current sensor reading)\b", text, re.I)) or bool(re.search(r"\b(?:not live|not real.time|not current)\b", combined, re.I)), "Do not imply live sensor data")
    if "associated_asset_uri" in evidence:
        check("asset_uri", evidence["associated_asset_uri"] in text, "Requested asset URI must match")
    stats = evidence.get("quantitative_temporal_analytics")
    if stats and stats.get("status") == "OK":
        metrics = [
            ("mean", r"mean", "mean"),
            ("standard_deviation_population", r"standard deviation", "standard_deviation_population"),
            ("linear_regression_slope", r"(?:linear regression slope|regression slope)", "linear_regression_slope_per_simulation_minute"),
            ("endpoint_change", r"(?:endpoint change|net change)", "endpoint_change"),
        ]
        for name, label, field in metrics:
            actual = _number_after(text, label)
            check(name, actual is not None and _matches(actual, stats[field]), "Metric must be explicitly stated and match computed evidence")
        check("slope_time_basis", bool(re.search(r"per simulation minute", text, re.I)), "Slope units must refer to simulation time")
        if stats.get("history_truncated_by_limit"):
            check("history_truncation", bool(re.search(r"\btruncat", combined, re.I)), "Truncated history must be disclosed")
    failed = [x["check"] for x in checks if not x["passed"]]
    return {
        "status": "CHECKS_PASSED_LIMITED_SCOPE" if not failed else "FAILED",
        "scope": "selected_explicit_numeric_claims_and_required_caveats_only",
        "checked_count": len(checks),
        "failed_checks": failed,
        "checks": checks,
        "limitations": ["Does not verify arbitrary free-form factual claims",
                        "Does not verify source-system correctness or physical provenance"],
    }
