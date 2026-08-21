"""Start the process-sim OPC UA operational server."""

from __future__ import annotations

import argparse
import asyncio

from process_sim.backends.tep import TEPAdapter
from process_sim.protocols.opcua import OPCUAServer


async def main() -> None:
    parser = argparse.ArgumentParser(description="Start the process-sim OPC UA server")
    parser.add_argument(
        "--endpoint",
        default="opc.tcp://0.0.0.0:4841/process-sim/",
        help="OPC UA endpoint",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="TEP simulator random seed",
    )
    parser.add_argument(
        "--real-time-factor",
        type=float,
        default=1.0,
        help="Simulation real-time factor",
    )
    parser.add_argument(
        "--update-interval",
        type=float,
        default=1.0,
        help="Simulation update interval in seconds",
    )
    args = parser.parse_args()

    # OPC UA is the operational control boundary. The TEP backend therefore
    # runs in manual mode and accepts XMV commands only through OPC UA.
    simulator = TEPAdapter(random_seed=args.seed, control_mode="manual")
    server = OPCUAServer(
        simulator,
        endpoint=args.endpoint,
        real_time_factor=args.real_time_factor,
        update_interval_seconds=args.update_interval,
    )

    await server.start()
    print(f"OPC UA server started: {args.endpoint}", flush=True)
    print("Control mode: external_opcua", flush=True)
    print("Write TEP/ManipulatedVariables/XMV1..XMV12 from an external controller.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    try:
        while True:
            await asyncio.sleep(1.0)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await server.stop()
        simulator.reset()


if __name__ == "__main__":
    asyncio.run(main())
