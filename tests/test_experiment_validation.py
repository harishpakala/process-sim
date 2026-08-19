from process_sim.experiments import ExpectedFault, ExperimentValidator, GroundTruth
from process_sim.recording import Event


def test_fault_lifecycle_ground_truth_matches():
    ground_truth = GroundTruth(
        fault=ExpectedFault(
            fault_type="bias",
            target="XMEAS9",
            start_time_hours=1.0,
            duration_hours=0.5,
        )
    )
    events = [
        Event(
            run_id="run-1",
            simulation_time_hours=1.0,
            wall_time=None,
            event_type="FaultActivated",
            subject="XMEAS9",
            source="fault-manager",
            metadata={"fault_type": "bias"},
        ),
        Event(
            run_id="run-1",
            simulation_time_hours=1.5,
            wall_time=None,
            event_type="FaultDeactivated",
            subject="XMEAS9",
            source="fault-manager",
            metadata={"fault_type": "bias"},
        ),
    ]

    result = ExperimentValidator().validate_events(ground_truth, events)
    assert result.passed
    assert not result.failures


def test_fault_lifecycle_time_mismatch_fails():
    ground_truth = GroundTruth(
        fault=ExpectedFault("bias", "XMEAS9", 1.0, 0.5)
    )
    events = [
        Event(
            run_id="run-1",
            simulation_time_hours=1.1,
            wall_time=None,
            event_type="FaultActivated",
            subject="XMEAS9",
            source="fault-manager",
            metadata={"fault_type": "bias"},
        ),
    ]

    result = ExperimentValidator().validate_events(ground_truth, events)
    assert not result.passed
    assert any("activation time" in failure for failure in result.failures)
