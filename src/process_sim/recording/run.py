"""Run identity and provenance metadata for recorded simulations."""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RunManifest:
    """Metadata describing one simulation run and its provenance."""

    run_id: str
    simulator: str = "process-sim"
    backend: str | None = None
    backend_version: str | None = None
    random_seed: int | None = None
    real_time_factor: float | None = None
    scenario: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Record the wall-clock start time."""
        self.started_at = datetime.now(timezone.utc).isoformat()

    def complete(self) -> None:
        """Record the wall-clock completion time."""
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable manifest."""
        return {
            "run_id": self.run_id,
            "simulator": self.simulator,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "random_seed": self.random_seed,
            "real_time_factor": self.real_time_factor,
            "scenario": self.scenario,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": dict(self.metadata),
        }
