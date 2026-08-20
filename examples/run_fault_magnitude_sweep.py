"""Run paired fault/baseline experiments across fault magnitudes and seeds."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from process_sim.backends.tep import TEPAdapter
from process_sim.experiments import Experiment, ExperimentRunner, GroundTruth
from process_sim.faults import Scenario


def _load_run(root: Path, run_id: str) -> pd.DataFrame:
    path = root / run_id / "observations.parquet"
    if not path.is_file():
        raise RuntimeError(f"Observations file does not exist: {path}")
    return pd.read_parquet(path)


def _integral(time_hours: pd.Series, values: pd.Series) -> float:
    if len(values) < 2:
        return 0.0
    time = time_hours.to_numpy(dtype=float)
    data = values.to_numpy(dtype=float)
    return float(((data[:-1] + data[1:]) * 0.5 * (time[1:] - time[:-1])).sum())


def _metrics(fault_observations: pd.DataFrame, baseline_observations: pd.DataFrame,
             variable: str, start: float, end: float, post_window: float) -> dict[str, float | int | str]:
    fault = fault_observations[fault_observations["variable"] == variable][
        ["simulation_time_hours", "value"]
    ].rename(columns={"value": "fault_value"})
    baseline = baseline_observations[baseline_observations["variable"] == variable][
        ["simulation_time_hours", "value"]
    ].rename(columns={"value": "baseline_value"})
    if fault.empty or baseline.empty:
        raise RuntimeError(f"Variable not found in both runs: {variable}")
    aligned = fault.merge(baseline, on="simulation_time_hours", how="inner")
    if aligned.empty:
        raise RuntimeError(f"No matching timestamps for variable: {variable}")
    aligned = aligned.sort_values("simulation_time_hours").reset_index(drop=True)
    aligned["delta"] = aligned["fault_value"] - aligned["baseline_value"]
    windows = {
        "fault": aligned[(aligned["simulation_time_hours"] >= start) & (aligned["simulation_time_hours"] < end)],
        "post": aligned[(aligned["simulation_time_hours"] >= end) & (aligned["simulation_time_hours"] < end + post_window)],
    }
    result: dict[str, float | int | str] = {"variable": variable, "matched_samples": int(len(aligned))}
    for name, data in windows.items():
        data = data.dropna(subset=["delta"])
        if data.empty:
            metrics = {"n": 0, "mean_delta": float("nan"), "mae": float("nan"), "rmse": float("nan"),
                       "max_abs_delta": float("nan"), "time_of_max_abs_delta_hours": float("nan"),
                       "iae": float("nan"), "ise": float("nan")}
        else:
            delta = data["delta"].astype(float)
            max_index = delta.abs().idxmax()
            metrics = {
                "n": int(delta.size), "mean_delta": float(delta.mean()), "mae": float(delta.abs().mean()),
                "rmse": float((delta.pow(2).mean()) ** 0.5), "max_abs_delta": float(delta.abs().max()),
                "time_of_max_abs_delta_hours": float(data.loc[max_index, "simulation_time_hours"]),
                "iae": _integral(data["simulation_time_hours"], delta.abs()),
                "ise": _integral(data["simulation_time_hours"], delta.pow(2)),
            }
        for key, value in metrics.items():
            result[f"{name}_{key}"] = value
    return result


def _fault_experiment(base: Experiment, seed: int, magnitude: float) -> Experiment:
    metadata = dict(base.metadata)
    metadata.update({"magnitude_sweep": True, "fault_magnitude": magnitude,
                     "replication_seed": seed, "replication_base_experiment": base.experiment_id})
    return replace(base, experiment_id=f"{base.experiment_id}__magnitude_{magnitude:g}__seed_{seed}",
                   seed=seed, metadata=metadata)


def _scenario_with_magnitude(scenario: Scenario, target: str, magnitude: float) -> Scenario:
    faults = []
    changed = False
    for fault in scenario.faults:
        if fault.target == target and fault.magnitude is not None:
            faults.append(replace(fault, magnitude=magnitude,
                                  metadata={**fault.metadata, "magnitude_sweep": True,
                                             "base_magnitude": fault.magnitude}))
            changed = True
        else:
            faults.append(fault)
    if not changed:
        raise ValueError(f"No magnitude-bearing fault targets {target!r} in scenario {scenario.name!r}")
    return replace(scenario, faults=tuple(faults), metadata={**scenario.metadata,
                       "magnitude_sweep": True, "fault_magnitude": magnitude})


def _baseline_experiment(fault_experiment: Experiment, baseline_scenario: Scenario) -> Experiment:
    return Experiment(
        experiment_id=f"{fault_experiment.experiment_id}__baseline",
        scenario=baseline_scenario.name,
        seed=fault_experiment.seed,
        duration_hours=fault_experiment.duration_hours,
        ground_truth=GroundTruth(affected=(), related=fault_experiment.ground_truth.related,
                                 metadata={"role": "baseline", "magnitude_sweep": True}),
        metadata={"purpose": "paired_no_fault_baseline", "paired_fault_experiment": fault_experiment.experiment_id,
                  "replication_seed": fault_experiment.seed, "magnitude_sweep": True},
    )


def _run(experiment: Experiment, scenario: Scenario, output_dir: Path, interval: int) -> dict[str, Any]:
    simulator = TEPAdapter(random_seed=experiment.seed)
    runner = ExperimentRunner(simulator, experiment, scenario, output_dir=output_dir)
    return runner.run(record_interval_steps=interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run paired experiments across fault magnitudes and seeds")
    parser.add_argument("experiment")
    parser.add_argument("fault_scenario")
    parser.add_argument("baseline_scenario")
    parser.add_argument("--magnitudes", nargs="+", type=float, default=[1.0, 5.0, 10.0])
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
    parser.add_argument("--output", type=Path, default=Path("data/runs"))
    parser.add_argument("--summary", type=Path, default=Path("data/replications/reactor_cooling_bias_magnitude_sweep.csv"))
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--target", default="XMEAS9")
    parser.add_argument("--related", nargs="*", default=["XMV10", "XMEAS21"])
    parser.add_argument("--post-window", type=float, default=0.25)
    args = parser.parse_args()
    if args.interval < 1 or args.post_window <= 0:
        raise SystemExit("--interval must be >= 1 and --post-window must be positive")
    if any(magnitude <= 0 for magnitude in args.magnitudes):
        raise SystemExit("all magnitudes must be positive")

    magnitudes = list(dict.fromkeys(args.magnitudes))
    seeds = list(dict.fromkeys(args.seeds))
    base_experiment = Experiment.from_file(args.experiment)
    base_scenario = Scenario.from_file(args.fault_scenario)
    baseline_scenario = Scenario.from_file(args.baseline_scenario)
    if base_experiment.scenario != base_scenario.name:
        raise SystemExit(f"Fault experiment scenario {base_experiment.scenario!r} does not match loaded scenario {base_scenario.name!r}")
    if base_experiment.ground_truth.fault is None:
        raise SystemExit("The fault experiment must declare expected ground truth")
    fault_spec = base_experiment.ground_truth.fault
    if fault_spec.duration_hours is None:
        raise SystemExit("Expected fault duration is required")
    if fault_spec.target != args.target:
        raise SystemExit(f"Expected fault target {fault_spec.target!r} does not match --target {args.target!r}")

    start = fault_spec.start_time_hours
    end = start + fault_spec.duration_hours
    variables = list(dict.fromkeys([args.target, *args.related]))
    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    print("Fault-magnitude sweep")
    print(f"Base experiment: {base_experiment.experiment_id}")
    print(f"Magnitudes:      {', '.join(f'{m:g}' for m in magnitudes)}")
    print(f"Seeds:           {', '.join(str(s) for s in seeds)}")
    print(f"Fault window:    {start:.6f} -> {end:.6f} h")

    for magnitude in magnitudes:
        # Keep the scenario identity equal to the experiment's declared scenario.
        # The magnitude belongs to the fault object, not to the scenario name.
        scenario = _scenario_with_magnitude(base_scenario, args.target, magnitude)
        print(f"\n=== magnitude {magnitude:g} ===")
        for seed in seeds:
            experiment = _fault_experiment(base_experiment, seed, magnitude)
            baseline_experiment = _baseline_experiment(experiment, baseline_scenario)
            print(f"seed {seed}: running fault...")
            fault_result = _run(experiment, scenario, args.output, args.interval)
            print(f"  fault run:    {fault_result['run_id']}")
            print(f"seed {seed}: running baseline...")
            baseline_result = _run(baseline_experiment, baseline_scenario, args.output, args.interval)
            print(f"  baseline run: {baseline_result['run_id']}")
            fault_observations = _load_run(args.output, fault_result["run_id"])
            baseline_observations = _load_run(args.output, baseline_result["run_id"])
            for variable in variables:
                rows.append({"magnitude": magnitude, "seed": seed,
                             "fault_run_id": fault_result["run_id"],
                             "baseline_run_id": baseline_result["run_id"],
                             **_metrics(fault_observations, baseline_observations, variable,
                                       start, end, args.post_window)})
            runs.append({"magnitude": magnitude, "seed": seed,
                         "fault_run_id": fault_result["run_id"],
                         "baseline_run_id": baseline_result["run_id"]})

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    detailed = pd.DataFrame(rows)
    detailed.to_csv(args.summary, index=False)
    aggregate_fields = ["fault_mean_delta", "fault_rmse", "fault_max_abs_delta", "fault_iae", "fault_ise",
                        "post_mean_delta", "post_rmse", "post_max_abs_delta", "post_iae", "post_ise"]
    grouped = detailed.groupby(["magnitude", "variable"], sort=True)
    aggregate = grouped[aggregate_fields].agg(["mean", "std", "min", "max"])
    aggregate.columns = [f"{metric}_{stat}" for metric, stat in aggregate.columns]
    aggregate = aggregate.reset_index()
    for metric in aggregate_fields:
        mean = aggregate[f"{metric}_mean"]
        aggregate[f"{metric}_cv"] = aggregate[f"{metric}_std"] / mean.abs().where(mean.abs() > 0)
    aggregate_path = args.summary.with_name(f"{args.summary.stem}_aggregate{args.summary.suffix}")
    aggregate.to_csv(aggregate_path, index=False)
    manifest_path = args.summary.with_suffix(".json")
    manifest_path.write_text(json.dumps({"base_experiment": base_experiment.experiment_id,
        "fault_scenario": base_scenario.name, "baseline_scenario": baseline_scenario.name,
        "magnitudes": magnitudes, "seeds": seeds, "fault_window": {"start": start, "end": end},
        "post_window_hours": args.post_window, "record_interval_steps": args.interval,
        "variables": variables, "runs": runs,
        "outputs": {"detailed_csv": str(args.summary), "aggregate_csv": str(aggregate_path)}}, indent=2),
        encoding="utf-8")
    print(f"\nDetailed CSV:  {args.summary}")
    print(f"Aggregate CSV: {aggregate_path}")
    print(f"Manifest:      {manifest_path}")
    print("\nAggregate response metrics:")
    display_columns = ["magnitude", "variable", "fault_rmse_mean", "fault_rmse_std",
                       "fault_max_abs_delta_mean", "fault_iae_mean", "fault_ise_mean",
                       "post_rmse_mean", "post_iae_mean"]
    print(aggregate[display_columns].to_string(index=False))


if __name__ == "__main__":
    main()
