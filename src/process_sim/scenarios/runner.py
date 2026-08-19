"""Execute reproducible fault scenarios against a process simulator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from process_sim.faults import FaultManager, FaultType, Scenario
from process_sim.recording import SimulationRecorder, SimulationRecordingSession
from process_sim.recording.run import RunManifest


class ScenarioRunner:
    """Run a :class:`Scenario` with recording and fault lifecycle events."""

    def __init__(self, simulator: Any, scenario: Scenario, output_dir: str | Path = "data/runs"):
        self.simulator = simulator
        self.scenario = scenario
        self.output_dir = Path(output_dir)
        self.fault_manager = FaultManager()
        for fault in scenario.faults:
            self.fault_manager.add(fault)

        self.recorder = SimulationRecorder()
        self.manifest = RunManifest(
            run_id=self.recorder.run_id,
            simulator="TEP" if simulator.__class__.__name__ == "TEPAdapter" else "process-sim",
            backend=getattr(simulator, "backend", None),
            random_seed=getattr(getattr(simulator, "simulator", None), "random_seed", None),
            scenario=scenario.name,
            metadata=dict(scenario.metadata),
        )
        self.session = SimulationRecordingSession(
            simulator=simulator,
            recorder=self.recorder,
            manifest=self.manifest,
        )
        if hasattr(simulator, "configure_faults"):
            simulator.configure_faults(
                self.fault_manager,
                fault_event_sink=self.session.record_fault_event,
            )

    def _apply_process_disturbances(self) -> None:
        """Synchronize active process-disturbance faults with native TEP IDVs."""
        time_hours = self.simulator.get_time_hours()
        active = {
            fault.target: fault
            for fault in self.fault_manager.active_faults(time_hours)
            if fault.fault_type is FaultType.PROCESS_DISTURBANCE
        }

        managed_ids = getattr(self, "_managed_idvs", set())
        for target in managed_ids - set(active):
            self.simulator.set_disturbance(target, 0)

        current_ids = set()
        for fault in active.values():
            index = self._idv_index(fault.target, fault.metadata)
            self.simulator.set_disturbance(index, 1)
            current_ids.add(index)
        self._managed_idvs = current_ids

    @staticmethod
    def _idv_index(target: str, metadata: dict) -> int:
        if target.upper().startswith("IDV"):
            index = int(target[3:])
        elif "idv_index" in metadata:
            index = int(metadata["idv_index"])
        else:
            raise ValueError(
                "process_disturbance faults require target='IDV1'..'IDV20' "
                "or metadata.idv_index"
            )
        if not 1 <= index <= 20:
            raise ValueError("IDV index must be in the range 1..20")
        return index

    def run(self, duration_hours: float, record_interval_steps: int = 1) -> dict:
        """Run the scenario and persist the complete recorded run."""
        if duration_hours < 0:
            raise ValueError("duration_hours must be >= 0")
        if record_interval_steps < 1:
            raise ValueError("record_interval_steps must be >= 1")

        self.session.start()
        self.session.record_snapshot()
        total_steps = int(round(duration_hours * 3600))

        for step_number in range(1, total_steps + 1):
            self._apply_process_disturbances()
            self.simulator.step()
            if step_number % record_interval_steps == 0:
                self.session.record_snapshot()

        self._apply_process_disturbances()
        self.session.complete()
        return self.session.save(
            metadata={
                "duration_hours": duration_hours,
                "native_step_seconds": 1,
                "record_interval_steps": record_interval_steps,
            }
        )
