"""Run the process-sim OPC UA server with the TEP simulator."""

from __future__ import annotations

import asyncio
from pathlib import Path

from process_sim.backends.tep import TEPAdapter
from process_sim.recording import (
    ParquetStorage,
    SimulationRecorder,
    SimulationRecordingSession,
)

from .server import OPCUAServer


async def main() -> None:
    """Start OPC UA and record operator events until the server stops."""
    simulator = TEPAdapter()
    simulator.reset()

    recorder = SimulationRecorder()
    session = SimulationRecordingSession(
        simulator,
        recorder=recorder,
        storage=ParquetStorage(Path("data") / "runs"),
    )

    def record_xmv_change(index: int, old_value: float, new_value: float) -> None:
        session.record_event(
            "ManipulatedVariableChanged",
            f"XMV{index}",
            source="opcua",
            predicate="changedTo",
            object=str(new_value),
            metadata={
                "old_value": old_value,
                "new_value": new_value,
                "actor": "opcua-client",
            },
        )

    server = OPCUAServer(
        simulator,
        real_time_factor=1.0,
        update_interval_seconds=1.0,
        event_callback=record_xmv_change,
    )
    await server.start()
    session.start()

    print("OPC UA server started")
    print(f"Endpoint: {server.endpoint}")
    print("Namespace: urn:process-sim:opcua")
    print("Simulation: stopped; use Simulation.Start() to run")
    print("Operator XMV changes will be recorded as events.")
    print("Press Ctrl+C to stop and save the recording.")

    try:
        await server.run()
    except asyncio.CancelledError:
        raise
    finally:
        session.complete()
        paths = session.save(
            metadata={
                "backend": simulator.backend,
                "recording_mode": "opcua-live",
                "event_source": "opcua",
            }
        )
        print("Recording saved.")
        for name, path in paths.items():
            print(f"{name}: {path}")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
