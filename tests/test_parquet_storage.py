from pathlib import Path

from process_sim.recording import ParquetStorage, SimulationRecorder


def test_write_run(tmp_path: Path):
    recorder = SimulationRecorder(run_id="run-001")
    recorder.record_observation(1.25, "XMEAS9", 122.38, unit="degC")
    recorder.record_observation(1.25, "XMV10", 20.0)
    recorder.record_event(
        1.25,
        "ManipulatedVariableChanged",
        "XMV10",
        source="opcua",
        metadata={"old_value": 16.0, "new_value": 20.0},
    )

    storage = ParquetStorage(tmp_path / "runs")
    paths = storage.write_run(
        recorder.run_id,
        recorder.observations(),
        recorder.events(),
        metadata={"backend": "tep", "real_time_factor": 1.0},
    )

    assert paths["observations"].exists()
    assert paths["events"].exists()
    assert paths["metadata"].exists()

    import pandas as pd

    observations = pd.read_parquet(paths["observations"])
    events = pd.read_parquet(paths["events"])

    assert len(observations) == 2
    assert observations.loc[0, "variable"] == "XMEAS9"
    assert observations.loc[0, "value"] == 122.38
    assert len(events) == 1
    assert events.loc[0, "event_type"] == "ManipulatedVariableChanged"
    assert '"new_value": 20.0' in events.loc[0, "metadata"]
