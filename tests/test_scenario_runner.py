from pathlib import Path

from process_sim.faults import Fault, FaultType, Scenario
from process_sim.scenarios.runner import ScenarioRunner


class FakeSimulator:
    backend = "fake"
    random_seed = 7

    def __init__(self):
        self.time_hours = 0.0
        self.steps = 0

    def get_time_hours(self):
        return self.time_hours

    def get_measurements(self):
        return [float(index) for index in range(1, 42)]

    def get_manipulated_variables(self):
        return [float(index) for index in range(1, 13)]

    def step(self):
        self.steps += 1
        self.time_hours += 1.0 / 3600.0
        return True


def test_runner_uses_output_dir_and_records_expected_snapshots(tmp_path: Path):
    scenario = Scenario(name="normal", faults=())
    simulator = FakeSimulator()

    result = ScenarioRunner(simulator, scenario, output_dir=tmp_path).run(
        duration_hours=2.0 / 3600.0,
        record_interval_steps=1,
    )

    run_dir = tmp_path / next(path.name for path in tmp_path.iterdir())
    assert result["observations"].parent == run_dir
    assert result["events"].parent == run_dir
    assert result["metadata"].parent == run_dir
    assert simulator.steps == 2

    import pandas as pd

    observations = pd.read_parquet(result["observations"])
    events = pd.read_parquet(result["events"])
    assert len(observations) == 3 * 53
    assert list(events["event_type"]) == ["SimulationStarted", "SimulationCompleted"]


def test_runner_does_not_duplicate_fault_configuration():
    class ConfigurableSimulator(FakeSimulator):
        def __init__(self):
            super().__init__()
            self.configure_calls = 0
            self.sync_calls = 0

        def configure_faults(self, fault_manager, fault_event_sink=None):
            self.configure_calls += 1
            self.fault_manager = fault_manager
            self.fault_event_sink = fault_event_sink

        def sync_faults(self):
            self.sync_calls += 1

    scenario = Scenario(
        name="fault",
        faults=(
            Fault(
                fault_id="f1",
                fault_type=FaultType.BIAS,
                target="XMEAS9",
                magnitude=5.0,
            ),
        ),
    )
    simulator = ConfigurableSimulator()
    runner = ScenarioRunner(simulator, scenario)

    assert simulator.configure_calls == 1
    runner.run(duration_hours=1.0 / 3600.0)
    assert simulator.sync_calls == 2
