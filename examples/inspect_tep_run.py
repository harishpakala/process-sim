"""Inspect a recorded TEP run stored as Parquet files.

Examples
--------
python examples/inspect_tep_run.py
python examples/inspect_tep_run.py --run-id <run-id>
"""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a recorded TEP run")
    parser.add_argument(
        "--run-id",
        help="Run ID under data/runs; defaults to the most recently modified run",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data") / "runs",
        help="Root directory containing recorded runs",
    )
    args = parser.parse_args()

    if args.run_id:
        run_dir = args.root / args.run_id
    else:
        run_dirs = [path for path in args.root.iterdir() if path.is_dir()]
        if not run_dirs:
            raise SystemExit(f"No recorded runs found under {args.root}")
        run_dir = max(run_dirs, key=lambda path: path.stat().st_mtime)

    if not run_dir.is_dir():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    observations_path = run_dir / "observations.parquet"
    events_path = run_dir / "events.parquet"
    metadata_path = run_dir / "metadata.json"

    observations = pd.read_parquet(observations_path)
    events = pd.read_parquet(events_path)

    print(f"Run: {run_dir.name}")
    print(f"Observation rows: {len(observations):,}")
    print(f"Event rows: {len(events):,}")

    if not observations.empty:
        print(
            "Simulation time: "
            f"{observations['simulation_time_hours'].min():.6f} -> "
            f"{observations['simulation_time_hours'].max():.6f} h"
        )
        print(f"Variables: {observations['variable'].nunique()}")
        print("Variable names:")
        print(", ".join(observations["variable"].drop_duplicates().tolist()))
        print("\nFirst observations:")
        print(observations.head(10).to_string(index=False))

    print("\nEvents:")
    if events.empty:
        print("No events recorded.")
    else:
        print(events.to_string(index=False))

    if metadata_path.exists():
        print("\nMetadata:")
        print(json.dumps(json.loads(metadata_path.read_text(encoding="utf-8")), indent=2))


if __name__ == "__main__":
    main()
