"""Run a process-sim scenario from YAML or JSON."""

# Created: 2026-08-19
# Author: Harish

import argparse

from process_sim.backends.tep import TEPAdapter
from process_sim.faults import Scenario
from process_sim.scenarios import ScenarioRunner


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="Path to a .yaml, .yml, or .json scenario")
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--backend", choices=("python", "fortran"), default="python")
    parser.add_argument("--output", default="data/runs")
    args = parser.parse_args()

    scenario = Scenario.from_file(args.scenario)
    simulator = TEPAdapter(backend=args.backend, random_seed=args.seed)
    result = ScenarioRunner(simulator, scenario, output_dir=args.output).run(
        duration_hours=args.hours,
        record_interval_steps=args.interval,
    )

    print(f"Run: {result['run_id']}")
    print(f"Scenario: {scenario.name}")
    print(f"Observations: {result['observation_rows']}")
    print(f"Events: {result['event_rows']}")
    print(f"Run directory: {result['run_dir']}")


if __name__ == "__main__":
    main()
