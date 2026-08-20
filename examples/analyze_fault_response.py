"""Analyze variable response around a scheduled fault window.

Examples
--------
python examples/analyze_fault_response.py \
    --run-id <run-id> \
    --root data/runs \
    --target XMEAS9 \
    --related XMV10 XMEAS21

An optional baseline run can be supplied later for same-seed response
comparison:

python examples/analyze_fault_response.py \
    --run-id <fault-run-id> \
    --baseline-run-id <baseline-run-id> \
    --root data/runs \
    --target XMEAS9 \
    --related XMV10 XMEAS21

The analysis is deliberately descriptive. It does not claim causal effects
from a single run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


def _load_run(root: Path, run_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    run_dir = root / run_id
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    observations_path = run_dir / "observations.parquet"
    metadata_path = run_dir / "metadata.json"
    observations = pd.read_parquet(observations_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return observations, metadata


def _fault_window(metadata: dict[str, Any]) -> tuple[float, float]:
    ground_truth = metadata.get("metadata", {}).get("ground_truth", {})
    fault = ground_truth.get("fault", {})
    try:
        start = float(fault["start"])
        duration = float(fault["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("Ground-truth fault start/duration are required") from exc
    return start, start + duration


def _stats(series: pd.Series) -> dict[str, float]:
    values = series.dropna().astype(float)
    if values.empty:
        return {"n": 0, "mean": float("nan"), "std": float("nan"), "median": float("nan")}
    return {
        "n": int(values.size),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "median": float(values.median()),
    }


def _window_stats(
    observations: pd.DataFrame,
    variable: str,
    start: float,
    end: float,
    pre_window: float,
    post_window: float,
) -> dict[str, dict[str, float]]:
    data = observations[observations["variable"] == variable].copy()
    if data.empty:
        raise SystemExit(f"Variable not found in observations: {variable}")

    pre = data[
        (data["simulation_time_hours"] >= start - pre_window)
        & (data["simulation_time_hours"] < start)
    ]["value"]
    fault = data[
        (data["simulation_time_hours"] >= start)
        & (data["simulation_time_hours"] < end)
    ]["value"]
    post = data[
        (data["simulation_time_hours"] >= end)
        & (data["simulation_time_hours"] < end + post_window)
    ]["value"]

    return {
        "pre_fault": _stats(pre),
        "fault": _stats(fault),
        "post_fault": _stats(post),
    }


def _delta(left: dict[str, float], right: dict[str, float]) -> float:
    return right["mean"] - left["mean"]


def _print_result(variable: str, stats: dict[str, dict[str, float]]) -> dict[str, Any]:
    pre = stats["pre_fault"]
    fault = stats["fault"]
    post = stats["post_fault"]
    result = {
        "variable": variable,
        "pre_fault": pre,
        "fault": fault,
        "post_fault": post,
        "fault_minus_pre_mean": _delta(pre, fault),
        "post_minus_pre_mean": _delta(pre, post),
        "post_minus_fault_mean": _delta(fault, post),
    }

    print(f"\n{variable}")
    print("  window       n        mean        std      median")
    for name in ("pre_fault", "fault", "post_fault"):
        row = result[name]
        print(
            f"  {name:<11} {int(row['n']):>6} "
            f"{row['mean']:>10.4f} {row['std']:>10.4f} {row['median']:>10.4f}"
        )
    print(f"  fault - pre mean: {result['fault_minus_pre_mean']:.4f}")
    print(f"  post  - pre mean: {result['post_minus_pre_mean']:.4f}")
    print(f"  post  - fault mean: {result['post_minus_fault_mean']:.4f}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze response around a controlled fault")
    parser.add_argument("--run-id", required=True, help="Fault experiment run ID")
    parser.add_argument("--baseline-run-id", help="Optional no-fault baseline run ID")
    parser.add_argument("--root", type=Path, default=Path("data") / "runs")
    parser.add_argument("--target", default="XMEAS9")
    parser.add_argument("--related", nargs="*", default=["XMV10", "XMEAS21"])
    parser.add_argument("--pre-window", type=float, default=0.25)
    parser.add_argument("--post-window", type=float, default=0.25)
    parser.add_argument("--json", action="store_true", help="Also print JSON results")
    args = parser.parse_args()

    if args.pre_window <= 0 or args.post_window <= 0:
        raise SystemExit("Window lengths must be positive")

    observations, metadata = _load_run(args.root, args.run_id)
    start, end = _fault_window(metadata)

    print(f"Run: {args.run_id}")
    print(f"Fault window: {start:.6f} -> {end:.6f} h")
    print(f"Pre window:   {start - args.pre_window:.6f} -> {start:.6f} h")
    print(f"Post window:  {end:.6f} -> {end + args.post_window:.6f} h")
    print("\nThis is descriptive single-run analysis; no causal claim is made.")

    variables = [args.target, *args.related]
    results: list[dict[str, Any]] = []
    for variable in dict.fromkeys(variables):
        stats = _window_stats(
            observations,
            variable,
            start,
            end,
            args.pre_window,
            args.post_window,
        )
        results.append(_print_result(variable, stats))

    if args.baseline_run_id:
        baseline, _ = _load_run(args.root, args.baseline_run_id)
        print(f"\nBaseline run: {args.baseline_run_id}")
        print("Baseline comparison uses the same simulation-time windows.")
        for variable in dict.fromkeys(variables):
            stats = _window_stats(
                baseline,
                variable,
                start,
                end,
                args.pre_window,
                args.post_window,
            )
            _print_result(f"baseline:{variable}", stats)

    if args.json:
        print("\nJSON:")
        print(json.dumps({"run_id": args.run_id, "fault_start": start, "fault_end": end, "results": results}, indent=2))


if __name__ == "__main__":
    main()
