"""Run the process-sim OPC UA server with the TEP simulator."""

from __future__ import annotations

import asyncio

from process_sim.backends.tep import TEPAdapter

from .server import OPCUAServer


async def main() -> None:
    """Start OPC UA and run the TEP simulation at 1x real time."""
    simulator = TEPAdapter()
    simulator.reset()

    server = OPCUAServer(simulator)
    await server.start()
    await server.update(running=True)

    print("OPC UA server started")
    print(f"Endpoint: {server.endpoint}")
    print("Namespace: urn:process-sim:opcua")
    print("Simulation: 1x real time")
    print("Press Ctrl+C to stop.")

    try:
        await server.run_simulation(
            real_time_factor=1.0,
            update_interval_seconds=1.0,
        )
    except asyncio.CancelledError:
        raise
    finally:
        await server.update(running=False)
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
