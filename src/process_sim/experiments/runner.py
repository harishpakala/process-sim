"""Execute declarative experiments and persist their ground truth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from process_sim.faults import Scenario
from process_sim.scenarios.runner import ScenarioRunner

from .models import Experiment


class ExperimentRunner:
    """Bridge an :class:`Experiment` to the existing ScenarioRunner.

    The experiment layer adds scientific context; ScenarioRunner remains the
    single owner of simulation orchestration, fault synchronization, recording,
    and run storage.
    """

    def __init__(
        self,
        simulator: Any,
        experiment: Experiment,
        scenario: Scenario,
        output_dir: str | Path = "data/runs",
    ) -> None:
        if scenario.name != experiment.scenario:
            raise ValueError(
                f"experiment scenario {experiment.scenario!r} does not match "
                f"loaded scenario {scenario.name!r}"
            )
        self.simulator = simulator
        self.experiment = experiment
        self.scenario = scenario
        self.runner = ScenarioRunner(simulator, scenario, output_dir=output_dir)

        # Keep experimental provenance with the run manifest without changing
        # ScenarioRunner's responsibilities.
        self.runner.manifest.metadata.update(
            {
                "experiment": experiment.to_dict(),
                "ground_truth": experiment.ground_truth.to_dict(),
            }
        )

    def run(self, record_interval_steps: int = 1) -> dict:
        """Execute the experiment for its declared duration."""
        return self.runner.run(
            duration_hours=self.experiment.duration_hours,
            record_interval_steps=record_interval_steps,
        )

    @classmethod
    def from_files(
        cls,
        simulator: Any,
        experiment_path: str | Path,
        scenario_path: str | Path,
        output_dir: str | Path = "data/runs",
    ) -> "ExperimentRunner":
        """Build an experiment runner from YAML/JSON specifications."""
        experiment = Experiment.from_file(experiment_path)
        scenario = Scenario.from_file(scenario_path)
        return cls(simulator, experiment, scenario, output_dir=output_dir)
