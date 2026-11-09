"""Created: 2026-08-19
Author: Harish"""

from pathlib import Path

from process_sim.faults import FaultType, Scenario


def test_scenario_from_dict():
    scenario = Scenario.from_dict(
        {
            "scenario": "reactor_sensor_bias",
            "faults": [
                {
                    "id": "f1",
                    "type": "bias",
                    "target": "XMEAS9",
                    "magnitude": 5,
                    "start": 1,
                    "duration": 0.5,
                }
            ],
        }
    )

    assert scenario.name == "reactor_sensor_bias"
    assert len(scenario.faults) == 1
    assert scenario.faults[0].fault_type is FaultType.BIAS
    assert scenario.faults[0].start_time_hours == 1.0


def test_scenario_from_yaml(tmp_path: Path):
    path = tmp_path / "scenario.yaml"
    path.write_text(
        """scenario: valve_stuck\nfaults:\n  - id: f1\n    type: stuck\n    target: XMV10\n    value: 20\n    start: 2\n""",
        encoding="utf-8",
    )

    scenario = Scenario.from_file(path)

    assert scenario.name == "valve_stuck"
    assert scenario.faults[0].value == 20.0
