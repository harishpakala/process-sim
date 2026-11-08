"""Created: 2026-08-19
Author: Harish"""

from process_sim.recording import SimulationRecorder


def test_record_observation_and_event():
    recorder = SimulationRecorder(run_id="run-001")

    observation = recorder.record_observation(
        1.25,
        "XMEAS9",
        122.38,
        unit="degC",
    )
    event = recorder.record_event(
        1.25,
        "ManipulatedVariableChanged",
        "XMV10",
        source="opcua",
        metadata={"old_value": 16.0, "new_value": 20.0},
    )

    assert observation.run_id == "run-001"
    assert observation.variable == "XMEAS9"
    assert observation.value == 122.38
    assert event.run_id == "run-001"
    assert event.event_type == "ManipulatedVariableChanged"
    assert event.subject == "XMV10"
    assert event.metadata["new_value"] == 20.0


def test_clear_retains_run_id():
    recorder = SimulationRecorder(run_id="run-002")
    recorder.record_observation(0.0, "XMV10", 16.0)
    recorder.record_event(0.0, "SimulationStarted", "Run", source="simulation")

    recorder.clear()

    assert recorder.run_id == "run-002"
    assert recorder.observations() == ()
    assert recorder.events() == ()
