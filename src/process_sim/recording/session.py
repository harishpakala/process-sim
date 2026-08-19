"""Helpers for recording live simulator state."""

from __future__ import annotations

from typing import Any

from .parquet import ParquetStorage
from .recorder import SimulationRecorder


class SimulationRecordingSession:
    """Connect a process simulator to a recorder and persistent storage.

    The session is intentionally pull-based: callers decide when a snapshot
    is recorded. It never advances or controls the simulator.
    """

    def __init__(
        self,
        simulator: Any,
        recorder: SimulationRecorder | None = None,
        storage: ParquetStorage | None = None,
    ) -> None:
        self.simulator = simulator
        self.recorder = recorder or SimulationRecorder()
        self.storage = storage or ParquetStorage()

    def record_snapshot(self) -> None:
        """Record the simulator's current XMEAS and XMV values.

        TEP measurement units come from the TEP backend mapping. Manipulated
        variables are currently recorded without a unit because the reference
        API documents their descriptions but does not define a consistent
        engineering unit for the valve/actuator values.
        """
        simulation_time = self.simulator.get_time_hours()

        # Keep TEP-specific metadata at the backend boundary rather than
        # making the generic recorder aware of XMEAS/XMV terminology.
        from process_sim.backends.tep.mapping import MEASUREMENT_UNITS

        for index, value in enumerate(self.simulator.get_measurements(), start=1):
            self.recorder.record_observation(
                simulation_time,
                f"XMEAS{index}",
                value,
                unit=MEASUREMENT_UNITS.get(index),
            )

        for index, value in enumerate(self.simulator.get_manipulated_variables(), start=1):
            self.recorder.record_observation(
                simulation_time,
                f"XMV{index}",
                value,
            )

    def record_event(self, *args, **kwargs):
        """Record a semantic event associated with the current simulation time."""
        kwargs.setdefault("source", "simulation")
        return self.recorder.record_event(
            self.simulator.get_time_hours(),
            *args,
            **kwargs,
        )

    def save(self, metadata: dict | None = None) -> dict:
        """Persist the current run and return the created file paths."""
        return self.storage.write_run(
            self.recorder.run_id,
            self.recorder.observations(),
            self.recorder.events(),
            metadata=metadata,
        )
