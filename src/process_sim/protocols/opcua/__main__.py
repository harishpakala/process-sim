"""Run the process-sim OPC UA server with the TEP simulator."""

from __future__ import annotations

import asyncio

from process_sim.backends.tep import TEPAdapter

from .server import OPCUAServer


async def main() -> None:
    """Start OPC UA and wait for simulation commands from the client."""
    simulator = TEPAdapter()
    simulator.reset()

    server = OPCUAServer(
        simulator,
        real_time_factor=1.0,
        update_interval_seconds=1.0,
    )
    await server.start()

    print("OPC UA server started")
    print(f"Endpoint: {server.endpoint}")
    print("Namespace: urn:process-sim:opcua")
    print("Simulation: stopped; use Simulation.Start() to run")
    print("Press Ctrl+C to stop.")

    try:
        await server.run()
    except asyncio.CancelledError:
        raise
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
