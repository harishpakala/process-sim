"""Parquet persistence for recorded simulation data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import Event, Observation


class ParquetStorage:
    """Persist canonical recording models as Parquet files.

    One run is stored in its own directory containing observations, events,
    and a small JSON metadata document. The storage layer is intentionally
    independent from the simulator and recorder orchestration.
    """

    def __init__(self, root: str | Path = "data/runs") -> None:
        self.root = Path(root)

    def run_directory(self, run_id: str) -> Path:
        """Return the directory used to persist one simulation run."""
        return self.root / run_id

    def write_observations(self, run_id: str, observations: Iterable[Observation]) -> Path:
        """Write observations for a run to ``observations.parquet``."""
        import pandas as pd

        rows = [
            {
                "run_id": item.run_id,
                "simulation_time_hours": item.simulation_time_hours,
                "wall_time": item.wall_time,
                "variable": item.variable,
                "value": item.value,
                "unit": item.unit,
                "quality": item.quality,
                "source": item.source,
            }
            for item in observations
        ]
        path = self._prepare_run_directory(run_id) / "observations.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False)
        return path

    def write_events(self, run_id: str, events: Iterable[Event]) -> Path:
        """Write events for a run to ``events.parquet``."""
        import pandas as pd

        rows = [
            {
                "run_id": item.run_id,
                "simulation_time_hours": item.simulation_time_hours,
                "wall_time": item.wall_time,
                "event_type": item.event_type,
                "subject": item.subject,
                "predicate": item.predicate,
                "object": item.object,
                "source": item.source,
                "metadata": json.dumps(dict(item.metadata), sort_keys=True),
            }
            for item in events
        ]
        path = self._prepare_run_directory(run_id) / "events.parquet"
        pd.DataFrame(rows).to_parquet(path, index=False)
        return path

    def write_metadata(self, run_id: str, metadata: dict) -> Path:
        """Write run metadata to ``metadata.json``."""
        path = self._prepare_run_directory(run_id) / "metadata.json"
        path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _prepare_run_directory(self, run_id: str) -> Path:
        path = self.run_directory(run_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_run(
        self,
        run_id: str,
        observations: Iterable[Observation],
        events: Iterable[Event],
        metadata: dict | None = None,
    ) -> dict[str, Path]:
        """Persist all recording data for one run and return created paths."""
        paths = {
            "observations": self.write_observations(run_id, observations),
            "events": self.write_events(run_id, events),
        }
        if metadata is not None:
            paths["metadata"] = self.write_metadata(run_id, metadata)
        return paths
