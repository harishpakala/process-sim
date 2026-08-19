"""Backend-independent simulation recorder."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .models import Event, Observation


class SimulationRecorder:
    """Collect observations and events without controlling the simulator.

    The recorder deliberately stores data in memory for the first iteration.
    A storage backend can consume these canonical models later.
    """

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or str(uuid4())
        self._observations: list[Observation] = []
        self._events: list[Event] = []

    @staticmethod
    def _wall_time() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_observation(
        self,
        simulation_time_hours: float,
        variable: str,
        value: float,
        *,
        unit: str | None = None,
        quality: str | None = None,
        source: str = "simulation",
        wall_time: str | None = None,
    ) -> Observation:
        """Record one timestamped observation."""
        observation = Observation(
            run_id=self.run_id,
            simulation_time_hours=float(simulation_time_hours),
            wall_time=wall_time or self._wall_time(),
            variable=variable,
            value=float(value),
            unit=unit,
            quality=quality,
            source=source,
        )
        self._observations.append(observation)
        return observation

    def record_event(
        self,
        simulation_time_hours: float,
        event_type: str,
        subject: str,
        *,
        source: str,
        predicate: str | None = None,
        object: str | None = None,
        metadata: dict | None = None,
        wall_time: str | None = None,
    ) -> Event:
        """Record one discrete event."""
        event = Event(
            run_id=self.run_id,
            simulation_time_hours=float(simulation_time_hours),
            wall_time=wall_time or self._wall_time(),
            event_type=event_type,
            subject=subject,
            source=source,
            predicate=predicate,
            object=object,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def observations(self) -> tuple[Observation, ...]:
        """Return recorded observations in insertion order."""
        return tuple(self._observations)

    def events(self) -> tuple[Event, ...]:
        """Return recorded events in insertion order."""
        return tuple(self._events)

    def clear(self) -> None:
        """Clear recorded data while retaining the current run ID."""
        self._observations.clear()
        self._events.clear()
