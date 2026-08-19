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
    RunManifest,
    SimulationRecorder,
    SimulationRecordingSession,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a TEP simulation run")
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--backend", choices=("python", "fortran"), default="python")
    args = parser.parse_args()

    if args.hours <= 0:
        parser.error("--hours must be greater than zero")
    if args.interval < 1:
        parser.error("--interval must be at least 1")

    simulator = TEPAdapter(backend=args.backend, random_seed=args.seed)
    simulator.reset()

    recorder = SimulationRecorder()
    manifest = RunManifest(
        run_id=recorder.run_id,
        simulator="TEP",
        backend=simulator.backend,
        random_seed=args.seed,
        real_time_factor=1.0,
        metadata={"native_step_seconds": 1},
    )
    session = SimulationRecordingSession(
        simulator=simulator,
        recorder=recorder,
        storage=ParquetStorage(Path("data") / "runs"),
        manifest=manifest,
    )

    session.start()
    session.record_snapshot()

    total_steps = int(args.hours * 3600)
    for step in range(1, total_steps + 1):
        simulator.step()
        if step % args.interval == 0 or step == total_steps:
            session.record_snapshot()

    session.complete()
    paths = session.save(
        metadata={
            "duration_hours": args.hours,
            "record_interval_steps": args.interval,
        }
    )

    print("Recording complete.")
    print(f"Run ID: {recorder.run_id}")
    print(f"Simulation time: {simulator.get_time_hours():.6f} h")
    print(f"Snapshots: {len(recorder.observations()) // 53}")
    print(f"Events: {len(recorder.events())}")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
