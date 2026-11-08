"""Created: 2026-08-19
Author: Harish"""

from pathlib import Path

from process_sim.recording import ParquetStorage, SimulationRecorder, SimulationRecordingSession


class FakeSimulator:
    def get_time_hours(self):
        return 1.5

    def get_measurements(self):
        return [121.5, 98.4]

    def get_manipulated_variables(self):
        return [1.0, 2.0]


def test_record_snapshot_captures_xmeas_and_xmv():
    session = SimulationRecordingSession(
        FakeSimulator(),
        recorder=SimulationRecorder(run_id="run-session"),
    )

    session.record_snapshot()

    observations = session.recorder.observations()
    assert len(observations) == 4
    assert observations[0].variable == "XMEAS1"
    assert observations[0].value == 121.5
    assert observations[2].variable == "XMV1"
    assert observations[2].value == 1.0


def test_lifecycle_events_use_current_simulation_time():
    session = SimulationRecordingSession(
        FakeSimulator(),
        recorder=SimulationRecorder(run_id="run-lifecycle"),
    )

    session.start()
    session.complete()
    session.reset()

    events = session.recorder.events()
    assert [event.event_type for event in events] == [
        "SimulationStarted",
        "SimulationCompleted",
        "SimulationReset",
    ]
    assert all(event.subject == "Run" for event in events)
    assert all(event.simulation_time_hours == 1.5 for event in events)
    assert all(event.source == "simulation" for event in events)


def test_save_persists_recorded_run(tmp_path: Path):
    session = SimulationRecordingSession(
        FakeSimulator(),
        recorder=SimulationRecorder(run_id="run-session"),
        storage=ParquetStorage(tmp_path / "runs"),
    )
    session.start()
    session.record_snapshot()
    session.complete()

    paths = session.save(metadata={"backend": "fake"})

    assert paths["observations"].exists()
    assert paths["events"].exists()
    assert paths["metadata"].exists()
