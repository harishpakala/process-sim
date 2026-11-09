"""Deterministic quantitative analytics for TEP NEXUS simulation-time samples.

All slopes are per simulation minute. No claim of a physical trend or
verified engineering mapping is implied by these descriptive statistics.
"""

# Created: 2026-11-02
# Author: Harish
import math
import statistics


def summarize_history(samples, truncated=False):
    """Summarize ordered observation dicts with simulation_seconds and value.

    Reject nonfinite values, decreasing times, and repeated timestamps.
    Repeated timestamps cannot be used as independent time coordinates.
    """
    if not samples:
        return {"status": "INSUFFICIENT_DATA", "sample_count": 0,
                "reason": "No observations"}
    points = []
    for item in samples:
        t = float(item["simulation_seconds"])
        y = float(item["value"])
        if not (math.isfinite(t) and math.isfinite(y)):
            raise ValueError("Nonfinite observation")
        points.append((t, y))
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError("Simulation timestamps must be strictly increasing")
    ys = [y for _, y in points]
    result = {
        "status": "OK" if len(points) >= 2 else "INSUFFICIENT_DATA",
        "sample_count": len(points),
        "time_basis": "simulation_time",
        "slope_unit": "signal_value_per_simulation_minute",
        "mean": statistics.fmean(ys),
        "standard_deviation_population": statistics.pstdev(ys),
        "minimum": min(ys),
        "maximum": max(ys),
        "history_truncated_by_limit": bool(truncated),
    }
    if len(points) < 2:
        result["reason"] = "At least two distinct timestamps required"
        return result
    times = [(t - points[0][0]) / 60.0 for t, _ in points]
    mt = statistics.fmean(times)
    my = result["mean"]
    sxx = sum((t - mt) ** 2 for t in times)
    slope = sum((t - mt) * (y - my) for t, y in zip(times, ys)) / sxx
    result.update({
        "elapsed_simulation_minutes": times[-1],
        "endpoint_change": ys[-1] - ys[0],
        "endpoint_rate_per_simulation_minute":
            (ys[-1] - ys[0]) / times[-1],
        "linear_regression_slope_per_simulation_minute": slope,
        "regression_method": "ordinary_least_squares_unweighted",
        "trend_interpretation": "descriptive_only",
    })
    return result
