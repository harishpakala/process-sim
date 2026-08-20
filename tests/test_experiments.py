from pathlib import Path

from process_sim.experiments import ExpectedFault, Experiment, GroundTruth


def test_experiment_from_dict():
    experiment = Experiment.from_dict(
        {
            "experiment": {
                "id": "reactor_cooling_bias_001",
                "scenario": "reactor_sensor_bias",
                "seed": 42,
                "duration_hours": 2,
            },
            "expected": {
                "fault": {
                    "type": "sensor_bias",
                    "target": "XMEAS9",
                    "start": 1,
                    "duration": 0.5,
                },
                "affected": ["XMEAS9"],
                "related": ["XMV10", "XMEAS21"],
            },
        }
    )

    assert experiment.experiment_id == "reactor_cooling_bias_001"
    assert experiment.seed == 42
    assert experiment.duration_hours == 2.0
    assert experiment.ground_truth.fault == ExpectedFault(
        fault_type="sensor_bias",
        target="XMEAS9",
        start_time_hours=1.0,
        duration_hours=0.5,
    )
    assert experiment.ground_truth.affected == ("XMEAS9",)


def test_experiment_from_yaml(tmp_path: Path):
    path = tmp_path / "experiment.yaml"
    path.write_text(
        """experiment:\n  id: normal_001\n  scenario: normal\n  seed: 7\n  duration_hours: 1\nexpected:\n  affected: []\n""",
        encoding="utf-8",
    )

    experiment = Experiment.from_file(path)
    assert experiment.experiment_id == "normal_001"
    assert experiment.seed == 7
    assert experiment.ground_truth == GroundTruth()


def test_experiment_round_trip_shape():
    experiment = Experiment(
        experiment_id="normal_001",
        scenario="normal",
        seed=42,
        duration_hours=1,
        metadata={"purpose": "baseline"},
    )

    restored = Experiment.from_dict(experiment.to_dict())
    assert restored == experiment
