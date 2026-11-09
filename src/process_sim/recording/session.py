"""Helpers for recording live simulator state."""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

from typing import Any

from .parquet import ParquetStorage
from .recorder import SimulationRecorder
from .run import RunManifest


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
        manifest: RunManifest | None = None,
    ) -> None:
        self.simulator = simulator
        self.recorder = recorder or SimulationRecorder()
        self.storage = storage or ParquetStorage()
        self.manifest = manifest or RunManifest(run_id=self.recorder.run_id)

    def record_snapshot(self) -> None:
        """Record the simulator's current XMEAS and XMV values.

        TEP measurement units come from the TEP backend mapping. Manipulated
        variables are currently recorded without a unit because the reference
        API documents their descriptions but does not define a consistent
        engineering unit for the valve/actuator values.
        """
        simulation_time = self.simulator.get_time_hours()
        from process_sim.backends.tep.mapping import MEASUREMENT_UNITS

        for index, value in enumerate(self.simulator.get_measurements(), start=1):
            self.recorder.record_observation(
                simulation_time,
                f"XMEAS{index}",
                value,
                unit=MEASUREMENT_UNITS.get(index),
            )

        for index, value in enumerate(self.simulator.get_manipulated_variables(), start=1):
            self.recorder.record_observation(simulation_time, f"XMV{index}", value)

    def record_event(self, *args, **kwargs):
        """Record a semantic event associated with the current simulation time."""
        kwargs.setdefault("source", "simulation")
        return self.recorder.record_event(
            self.simulator.get_time_hours(), *args, **kwargs
        )

    def record_fault_event(self, event: dict):
        """Record a FaultManager lifecycle event through the canonical event model."""
        return self.recorder.record_event(
            event.get("simulation_time_hours", self.simulator.get_time_hours()),
            event["event_type"],
            event["target"],
            source="fault-manager",
            metadata={
                "fault_id": event["fault_id"],
                "fault_type": event["fault_type"],
                **event.get("metadata", {}),
            },
        )

    def start(self):
        """Record that the simulation run started and timestamp its manifest."""
        self.manifest.start()
        return self.record_event("SimulationStarted", "Run", source="simulation")

    def complete(self):
        """Record completion and timestamp the run manifest."""
        self.manifest.complete()
        return self.record_event("SimulationCompleted", "Run", source="simulation")

    def reset(self):
        """Record that the simulation was reset without controlling the simulator."""
        return self.record_event("SimulationReset", "Run", source="simulation")

    def save(self, metadata: dict | None = None) -> dict:
        """Persist observations, events, and the run manifest."""
        manifest_metadata = dict(self.manifest.metadata)
        if metadata:
            manifest_metadata.update(metadata)
        self.manifest.metadata = manifest_metadata
        return self.storage.write_run(
            self.recorder.run_id,
            self.recorder.observations(),
            self.recorder.events(),
            metadata=self.manifest.to_dict(),
        )
