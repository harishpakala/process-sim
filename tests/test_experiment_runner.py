from pathlib import Path

import pytest

from process_sim.experiments import Experiment, ExperimentRunner
from process_sim.faults import Scenario


def test_experiment_runner_rejects_scenario_mismatch():
    experiment = Experiment(
        experiment_id="exp-001",
        scenario="expected-scenario",
        duration_hours=0,
    )
    scenario = Scenario(name="different-scenario")

    with pytest.raises(ValueError, match="does not match"):
        ExperimentRunner(object(), experiment, scenario)


def test_experiment_runner_from_files_parses_specs(tmp_path: Path):
    experiment_path = tmp_path / "experiment.yaml"
    scenario_path = tmp_path / "scenario.yaml"
    experiment_path.write_text(
        """experiment:\n  id: exp-001\n  scenario: test-scenario\n  seed: 42\n  duration_hours: 0\nexpected:\n  affected: []\n""",
        encoding="utf-8",
    )
    scenario_path.write_text(
        """scenario: test-scenario\nfaults: []\n""",
        encoding="utf-8",
    )

    class DummySimulator:
        pass

    runner = ExperimentRunner.from_files(
        DummySimulator(), experiment_path, scenario_path
    )
    assert runner.experiment.experiment_id == "exp-001"
    assert runner.scenario.name == "test-scenario"
