"""Run the process-sim OPC UA server with the TEP simulator."""

from __future__ import annotations

import asyncio

from process_sim.backends.tep import TEPAdapter

from .server import OPCUAServer


async def main() -> None:
    """Start the OPC UA server and keep it running."""
    simulator = TEPAdapter()
    simulator.reset()

    server = OPCUAServer(simulator)
    await server.start()

    print("OPC UA server started")
    print(f"Endpoint: {server.endpoint}")
    print("Namespace: urn:process-sim:opcua")
    print("Press Ctrl+C to stop.")

    try:
        await server.run()
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
