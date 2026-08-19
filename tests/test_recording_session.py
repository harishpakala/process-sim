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


def test_save_persists_recorded_run(tmp_path: Path):
    session = SimulationRecordingSession(
        FakeSimulator(),
        recorder=SimulationRecorder(run_id="run-session"),
        storage=ParquetStorage(tmp_path / "runs"),
    )
    session.record_snapshot()
    session.record_event("SimulationStarted", "Run")

    paths = session.save(metadata={"backend": "fake"})

    assert paths["observations"].exists()
    assert paths["events"].exists()
    assert paths["metadata"].exists()
