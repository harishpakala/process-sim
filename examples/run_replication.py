"""Run paired fault/baseline replications and write a benchmark summary.

This script keeps the experimental protocol fixed while varying only the
random seed. For each seed it runs one fault experiment and one matching
no-fault baseline, aligns their observations on simulation time, and writes
one row per measured variable to a CSV summary.

Example
-------
python examples/run_replication.py \
    examples/experiments/reactor_cooling_bias_001.yaml \
    examples/scenarios/reactor_sensor_bias.yaml \
    examples/scenarios/reactor_no_fault.yaml \
    --seeds 42 43 44 45 46 \
    --output data/runs \
    --summary data/replications/reactor_cooling_bias.csv
"""

# Created: 2026-08-20
# Author: Harish

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


def _paired_metrics(
    fault_observations: pd.DataFrame,
    baseline_observations: pd.DataFrame,
    variable: str,
    start: float,
    end: float,
    post_window: float,
) -> dict[str, float | int | str]:
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

    aligned["delta"] = aligned["fault_value"] - aligned["baseline_value"]

    windows = {
        "fault": aligned[
            (aligned["simulation_time_hours"] >= start)
            & (aligned["simulation_time_hours"] < end)
        ],
        "post": aligned[
            (aligned["simulation_time_hours"] >= end)
            & (aligned["simulation_time_hours"] < end + post_window)
        ],
    }

    result: dict[str, float | int | str] = {
        "variable": variable,
        "matched_samples": int(len(aligned)),
    }

    for name, data in windows.items():
        delta = data["delta"].dropna().astype(float)
        if delta.empty:
            metrics = {
                "n": 0,
                "mean_delta": float("nan"),
                "mae": float("nan"),
                "rmse": float("nan"),
                "max_abs_delta": float("nan"),
                "time_of_max_abs_delta_hours": float("nan"),
            }
        else:
            max_index = delta.abs().idxmax()
            metrics = {
                "n": int(delta.size),
                "mean_delta": float(delta.mean()),
                "mae": float(delta.abs().mean()),
                "rmse": float((delta.pow(2).mean()) ** 0.5),
                "max_abs_delta": float(delta.abs().max()),
                "time_of_max_abs_delta_hours": float(
                    data.loc[max_index, "simulation_time_hours"]
                ),
            }

        for key, value in metrics.items():
            result[f"{name}_{key}"] = value

    return result


def _experiment_for_seed(
    experiment: Experiment,
    seed: int,
    experiment_id: str,
) -> Experiment:
    metadata = dict(experiment.metadata)
    metadata.update(
        {
            "replication_seed": seed,
            "replication_base_experiment": experiment.experiment_id,
        }
    )
    return replace(
        experiment,
        experiment_id=experiment_id,
        seed=seed,
        metadata=metadata,
    )


def _baseline_for_seed(
    fault_experiment: Experiment,
    baseline_scenario: Scenario,
    seed: int,
) -> Experiment:
    metadata = {
        "purpose": "paired_no_fault_baseline",
        "paired_fault_experiment": fault_experiment.experiment_id,
        "replication_seed": seed,
    }
    ground_truth = GroundTruth(
        affected=(),
        related=fault_experiment.ground_truth.related,
        metadata={"role": "baseline"},
    )
    return Experiment(
        experiment_id=f"{fault_experiment.experiment_id}__baseline__seed_{seed}",
        scenario=baseline_scenario.name,
        seed=seed,
        duration_hours=fault_experiment.duration_hours,
        ground_truth=ground_truth,
        metadata=metadata,
    )


def _run(
    experiment: Experiment,
    scenario: Scenario,
    output_dir: Path,
    record_interval_steps: int,
) -> dict[str, Any]:
    simulator = TEPAdapter(random_seed=experiment.seed)
    runner = ExperimentRunner(
        simulator,
        experiment,
        scenario,
        output_dir=output_dir,
    )
    return runner.run(record_interval_steps=record_interval_steps)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run paired fault/baseline replications across seeds"
    )
    parser.add_argument("experiment", help="Fault experiment YAML/JSON file")
    parser.add_argument("fault_scenario", help="Fault scenario YAML/JSON file")
    parser.add_argument("baseline_scenario", help="No-fault scenario YAML/JSON file")
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        required=True,
        help="Random seeds to replicate; each seed gets a paired baseline",
    )
    parser.add_argument("--output", type=Path, default=Path("data/runs"))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("data/replications/reactor_cooling_bias.csv"),
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Record every N native simulation steps",
    )
    parser.add_argument("--target", default="XMEAS9")
    parser.add_argument("--related", nargs="*", default=["XMV10", "XMEAS21"])
    parser.add_argument("--post-window", type=float, default=0.25)
    args = parser.parse_args()

    if args.interval < 1:
        raise SystemExit("--interval must be >= 1")
    if args.post_window <= 0:
        raise SystemExit("--post-window must be positive")

    seeds = list(dict.fromkeys(args.seeds))
    base_experiment = Experiment.from_file(args.experiment)
    fault_scenario = Scenario.from_file(args.fault_scenario)
    baseline_scenario = Scenario.from_file(args.baseline_scenario)

    if base_experiment.scenario != fault_scenario.name:
        raise SystemExit(
            f"Fault experiment scenario {base_experiment.scenario!r} does not "
            f"match loaded scenario {fault_scenario.name!r}"
        )

    if base_experiment.ground_truth.fault is None:
        raise SystemExit("The fault experiment must declare expected ground truth")

    fault_spec = base_experiment.ground_truth.fault
    start = fault_spec.start_time_hours
    if fault_spec.duration_hours is None:
        raise SystemExit("Expected fault duration is required for replication")
    end = start + fault_spec.duration_hours

    variables = list(dict.fromkeys([args.target, *args.related]))
    all_rows: list[dict[str, Any]] = []
    run_manifest: list[dict[str, Any]] = []

    print(f"Base experiment: {base_experiment.experiment_id}")
    print(f"Fault scenario:  {fault_scenario.name}")
    print(f"Baseline:       {baseline_scenario.name}")
    print(f"Seeds:           {', '.join(str(seed) for seed in seeds)}")
    print(f"Fault window:   {start:.6f} -> {end:.6f} h")

    for seed in seeds:
        fault_experiment = _experiment_for_seed(
            base_experiment,
            seed,
            f"{base_experiment.experiment_id}__seed_{seed}",
        )
        baseline_experiment = _baseline_for_seed(
            fault_experiment,
            baseline_scenario,
            seed,
        )

        print(f"\n=== seed {seed} ===")
        print("running fault experiment...")
        fault_result = _run(
            fault_experiment,
            fault_scenario,
            args.output,
            args.interval,
        )
        print(f"fault run:     {fault_result['run_id']}")

        print("running paired baseline...")
        baseline_result = _run(
            baseline_experiment,
            baseline_scenario,
            args.output,
            args.interval,
        )
        print(f"baseline run:  {baseline_result['run_id']}")

        fault_observations = _load_run(args.output, fault_result["run_id"])
        baseline_observations = _load_run(args.output, baseline_result["run_id"])

        for variable in variables:
            metrics = _paired_metrics(
                fault_observations,
                baseline_observations,
                variable,
                start,
                end,
                args.post_window,
            )
            all_rows.append(
                {
                    "seed": seed,
                    "fault_run_id": fault_result["run_id"],
                    "baseline_run_id": baseline_result["run_id"],
                    "fault_experiment_id": fault_experiment.experiment_id,
                    "baseline_experiment_id": baseline_experiment.experiment_id,
                    **metrics,
                }
            )

        run_manifest.append(
            {
                "seed": seed,
                "fault_run_id": fault_result["run_id"],
                "baseline_run_id": baseline_result["run_id"],
            }
        )

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(all_rows)
    summary.to_csv(args.summary, index=False)

    manifest_path = args.summary.with_suffix(".json")
    manifest_path.write_text(
        json.dumps(
            {
                "base_experiment": base_experiment.experiment_id,
                "fault_scenario": fault_scenario.name,
                "baseline_scenario": baseline_scenario.name,
                "seeds": seeds,
                "fault_window": {"start": start, "end": end},
                "post_window_hours": args.post_window,
                "record_interval_steps": args.interval,
                "variables": variables,
                "runs": run_manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nSummary CSV: {args.summary}")
    print(f"Manifest:    {manifest_path}")
    print("\nReplication summary:")
    print(
        summary[
            [
                "seed",
                "variable",
                "fault_mean_delta",
                "fault_rmse",
                "fault_max_abs_delta",
                "post_mean_delta",
                "post_rmse",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
