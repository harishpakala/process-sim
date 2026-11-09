"""Run a TEP simulation and persist observations to Parquet.

Examples
--------
python examples/record_tep_run.py --hours 1
python examples/record_tep_run.py --hours 2 --interval 10
"""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from process_sim.backends.tep import TEPAdapter
from process_sim.recording import (
    ParquetStorage,
    RunManifest,
    SimulationRecorder,
    SimulationRecordingSession,
)


EQUIPMENT_SIGNAL = re.compile(r"^(XMEAS|XMV)[_ (]*(\d+)\)?$", re.IGNORECASE)


def export_equipment_csv(observations, output: Path) -> None:
    """Pivot native recorded observations into a wide CSV for equipment screening."""
    rows: dict[float, dict[str, float]] = {}
    for obs in observations:
        match = EQUIPMENT_SIGNAL.fullmatch(obs.variable.strip())
        if not match:
            continue
        name = f"{match.group(1).upper()}({int(match.group(2))})"
        time = float(obs.simulation_time_hours)
        row = rows.setdefault(time, {"time": time})
        if name in row:
            raise ValueError(f"Duplicate {name} observation at time {time}")
        row[name] = float(obs.value)
    if not rows:
        raise ValueError("No XMEAS/XMV observations found; CSV not created")
    columns = sorted({key for row in rows.values() for key in row if key != "time"},
                     key=lambda key: (0 if key.startswith("XMEAS") else 1,
                                      int(key.split("(")[1].rstrip(")"))))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["time", *columns])
        writer.writeheader()
        for time in sorted(rows):
            writer.writerow(rows[time])


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a TEP simulation run")
    parser.add_argument("--hours", type=float, default=1.0)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--backend", choices=("python", "fortran"), default="python")
    parser.add_argument("--equipment-csv", type=Path, default=None,
                        help="Also export recorded XMEAS/XMV signals as a wide CSV (time in hours)")
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

    if args.equipment_csv is not None:
        export_equipment_csv(recorder.observations(), args.equipment_csv)
        print(f"Equipment CSV: {args.equipment_csv}")

    print("Recording complete.")
    print(f"Run ID: {recorder.run_id}")
    print(f"Simulation time: {simulator.get_time_hours():.6f} h")
    print(f"Snapshots: {len(recorder.observations()) // 53}")
    print(f"Events: {len(recorder.events())}")
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
