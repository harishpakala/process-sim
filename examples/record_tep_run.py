"""Run a TEP simulation and persist observations to Parquet.

Examples
--------
python examples/record_tep_run.py --hours 1
python examples/record_tep_run.py --hours 2 --interval 10
"""

from __future__ import annotations

import argparse
from pathlib import Path

from process_sim.backends.tep import TEPAdapter
from process_sim.recording import (
    ParquetStorage,
    SimulationRecorder,
    SimulationRecordingSession,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a TEP simulation run")
    parser.add_argument(
        "--hours",
        type=float,
        default=1.0,
        help="Simulation duration in hours (default: 1.0)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=1,
        help="Record every N simulation steps (default: 1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="TEP random seed (default: 42)",
    )
    parser.add_argument(
        "--backend",
        choices=("python", "fortran"),
        default="python",
        help="TEP numerical backend (default: python)",
    )
    args = parser.parse_args()

    if args.hours <= 0:
        parser.error("--hours must be greater than zero")
    if args.interval < 1:
        parser.error("--interval must be at least 1")

    simulator = TEPAdapter(
        backend=args.backend,
        random_seed=args.seed,
    )
    simulator.reset()

    recorder = SimulationRecorder()
    storage = ParquetStorage(Path("data") / "runs")
    session = SimulationRecordingSession(
        simulator=simulator,
        recorder=recorder,
        storage=storage,
    )

    # Record the initialized state at simulation time zero.
    session.record_snapshot()

    total_steps = int(args.hours * 3600)
    for step in range(1, total_steps + 1):
        simulator.step()

        if step % args.interval == 0 or step == total_steps:
            session.record_snapshot()

    paths = session.save(
        metadata={
            "backend": simulator.backend,
            "duration_hours": args.hours,
            "random_seed": args.seed,
            "record_interval_steps": args.interval,
            "native_step_seconds": 1,
        }
    )

    print("Recording complete.")
    print(f"Run ID: {recorder.run_id}")
    print(f"Simulation time: {simulator.get_time_hours():.6f} h")
    print(f"Snapshots: {len(recorder.observations()) // 53}")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
