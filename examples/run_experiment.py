"""Execute a declarative experiment specification."""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

import argparse

from process_sim.backends.tep import TEPAdapter
from process_sim.experiments import ExperimentRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a process-sim experiment")
    parser.add_argument("experiment", help="Experiment YAML/JSON file")
    parser.add_argument("scenario", help="Scenario YAML/JSON file")
    parser.add_argument("--output", default="data/runs", help="Run output directory")
    parser.add_argument(
        "--interval", type=int, default=1, help="Record every N native simulation steps"
    )
    args = parser.parse_args()

    from process_sim.experiments import Experiment

    experiment = Experiment.from_file(args.experiment)
    simulator = TEPAdapter(random_seed=experiment.seed)
    runner = ExperimentRunner.from_files(
        simulator,
        args.experiment,
        args.scenario,
        output_dir=args.output,
    )
    result = runner.run(record_interval_steps=args.interval)

    print(f"experiment: {experiment.experiment_id}")
    print(f"scenario:   {experiment.scenario}")
    print(f"run_id:     {result['run_id']}")
    print(f"output:     {args.output}")


if __name__ == "__main__":
    main()
