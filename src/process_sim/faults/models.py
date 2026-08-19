"""Canonical fault models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FaultType(str, Enum):
    """Fault mechanisms supported by the first fault-injection layer."""

    BIAS = "bias"
    DRIFT = "drift"
    STUCK = "stuck"
    PROCESS_DISTURBANCE = "process_disturbance"


@dataclass
class Fault:
    """A scheduled or active fault applied to a simulation target."""

    fault_id: str
    fault_type: FaultType
    target: str
    magnitude: float | None = None
    value: float | None = None
    start_time_hours: float = 0.0
    duration_hours: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_active(self, simulation_time_hours: float) -> bool:
        """Return whether this fault is active at the supplied simulation time."""
        if simulation_time_hours < self.start_time_hours:
            return False
        if self.duration_hours is None:
            return True
        return simulation_time_hours < self.start_time_hours + self.duration_hours
