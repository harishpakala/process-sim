"""Execute reproducible fault scenarios against a process simulator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from process_sim.faults import FaultManager, Scenario
from process_sim.recording import (
    ParquetStorage,
    SimulationRecorder,
    SimulationRecordingSession,
)
from process_sim.recording.run import RunManifest


class ScenarioRunner:
    """Run a :class:`Scenario` with recording and fault lifecycle events.

    The simulator remains the owner of simulator-specific fault application.
    The runner owns orchestration, recording cadence, provenance, and storage.
    """

    def __init__(
        self,
        simulator: Any,
        scenario: Scenario,
        output_dir: str | Path = "data/runs",
    ):
        self.simulator = simulator
        self.scenario = scenario
        self.output_dir = Path(output_dir)
        self.fault_manager = FaultManager()
        for fault in scenario.faults:
            self.fault_manager.add(fault)

        self.recorder = SimulationRecorder()
        self.manifest = RunManifest(
            run_id=self.recorder.run_id,
            simulator=(
                "TEP" if simulator.__class__.__name__ == "TEPAdapter" else "process-sim"
            ),
            backend=getattr(simulator, "backend", None),
            random_seed=getattr(simulator, "random_seed", None),
            scenario=scenario.name,
            metadata=dict(scenario.metadata),
        )
        self.session = SimulationRecordingSession(
            simulator=simulator,
            recorder=self.recorder,
            storage=ParquetStorage(self.output_dir),
            manifest=self.manifest,
        )
        if hasattr(simulator, "configure_faults"):
            simulator.configure_faults(
                self.fault_manager,
                fault_event_sink=self.session.record_fault_event,
            )

    def _sync_faults(self) -> None:
        """Synchronize simulator-managed faults at the current simulation time."""
        sync = getattr(self.simulator, "sync_faults", None)
        if sync is not None:
            sync()

    def run(self, duration_hours: float, record_interval_steps: int = 1) -> dict:
        """Run the scenario and persist the complete recorded run.

        Returns a stable run-result dictionary containing the run identifier
        and paths to the persisted artifacts. This keeps callers independent
        of the storage implementation's internal return shape.
        """
        if duration_hours < 0:
            raise ValueError("duration_hours must be >= 0")
        if record_interval_steps < 1:
            raise ValueError("record_interval_steps must be >= 1")

        self.session.start()
        self._sync_faults()
        self.session.record_snapshot()
        total_steps = int(round(duration_hours * 3600))

        for step_number in range(1, total_steps + 1):
            self.simulator.step()
            if step_number % record_interval_steps == 0:
                self.session.record_snapshot()

        # Flush lifecycle transitions at the exact final simulation boundary,
        # including a fault whose duration ends at the end of the run.
        self._sync_faults()
        self.session.complete()
        paths = self.session.save(
            metadata={
                "duration_hours": duration_hours,
                "native_step_seconds": 1,
                "record_interval_steps": record_interval_steps,
            }
        )
        return {
            "run_id": self.recorder.run_id,
            "paths": paths,
            "metadata": self.manifest.to_dict(),
        }
