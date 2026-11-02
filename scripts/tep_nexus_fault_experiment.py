#!/usr/bin/env python3
"""Execute one operator fault experiment through the existing OPC UA interface.

Does not start an OPC UA server, modify simulator internals, or fabricate a
historian run ID. A persisted run ID must be established independently.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from asyncua import Client, ua

NAMESPACE = "urn:process-sim:opcua"
DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:4841/process-sim/"
SIGNALS = ("XMEAS6", "XMEAS7", "XMEAS8", "XMEAS9")


async def child(parent, name):
    for node in await parent.get_children():
        if (await node.read_browse_name()).Name == name:
            return node
    raise LookupError(f"OPC UA node {name!r} not found")


async def call(parent, method_name, *args):
    return await parent.call_method(await child(parent, method_name), *args)


async def execute(endpoint, fault_id, fault_type, target, magnitude, duration,
                  onset, post_window, interval, start, stop, reset):
    async with Client(endpoint, timeout=10) as client:
        tep = await child(client.nodes.objects, "TEP")
        sim = await child(tep, "Simulation")
        faults = await child(tep, "FaultManagement")
        measures = await child(tep, "Measurements")
        time_node = await child(sim, "TimeHours")
        running_node = await child(sim, "Running")
        nodes = {signal: await child(measures, signal) for signal in SIGNALS}
        if reset:
            if await running_node.read_value():
                raise RuntimeError("Refusing Reset while simulation is running")
            if not await call(sim, "Reset"):
                raise RuntimeError("OPC UA Reset failed")
        if start and not await running_node.read_value():
            if not await call(sim, "Start"):
                raise RuntimeError("OPC UA Start failed")
        if not await running_node.read_value():
            raise RuntimeError("Simulation is not running; use --start")
        initial = float(await time_node.read_value())
        if onset <= initial:
            raise ValueError("Fault onset must be after the current simulation time")
        records = []
        injection = None
        last_time = initial
        try:
            while True:
                t = float(await time_node.read_value())
                if t < last_time:
                    raise RuntimeError("Simulation time moved backward during experiment")
                last_time = t
                values = {signal: float(await node.read_value()) for signal, node in nodes.items()}
                records.append({"simulation_seconds": t * 3600, "values": values})
                if injection is None and t >= onset:
                    args = [
                        ua.Variant(fault_id, ua.VariantType.String),
                        ua.Variant(fault_type, ua.VariantType.String),
                        ua.Variant(target, ua.VariantType.String),
                        ua.Variant(float(magnitude), ua.VariantType.Double),
                        ua.Variant(0.0, ua.VariantType.Double),
                        ua.Variant(float(duration), ua.VariantType.Double),
                    ]
                    if not await call(faults, "InjectFault", *args):
                        raise RuntimeError("OPC UA InjectFault returned false")
                    registered = json.loads(await call(faults, "ListFaults"))
                    match = next((f for f in registered if f["fault_id"] == fault_id), None)
                    if not match:
                        raise RuntimeError("Injected fault not found in OPC UA ListFaults")
                    injection = {"requested_onset_seconds": onset * 3600,
                                 "registered_fault": match,
                                 "confirmed_at_simulation_seconds": t * 3600}
                if injection and t >= injection["registered_fault"]["start_time_hours"] + post_window:
                    break
                if not await running_node.read_value():
                    raise RuntimeError("Simulation stopped before experiment completed")
                await asyncio.sleep(interval)
        finally:
            if stop:
                await call(sim, "Stop")
        return {"endpoint": endpoint, "fault_command_source": "opcua",
                "fault_id": fault_id, "injection": injection,
                "observations": records,
                "signals": list(SIGNALS),
                "recording_scope": "OPC UA client observations, not TimescaleDB verification",
                "run_id": None,
                "run_provenance": "NOT_VERIFIED",
                "generated_at_utc": datetime.now(timezone.utc).isoformat()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--fault-id", default=None)
    p.add_argument("--fault-type", choices=["bias", "drift", "stuck", "process_disturbance"], default="bias")
    p.add_argument("--target", default="XMEAS9")
    p.add_argument("--magnitude", type=float, default=5.0)
    p.add_argument("--duration-hours", type=float, default=0.05)
    p.add_argument("--onset-hours", type=float, required=True)
    p.add_argument("--post-window-hours", type=float, default=0.08)
    p.add_argument("--poll-seconds", type=float, default=0.5)
    p.add_argument("--start", action="store_true", help="Start existing server simulation")
    p.add_argument("--stop", action="store_true", help="Stop simulation after recording")
    p.add_argument("--reset", action="store_true", help="Reset before starting; requires stopped simulation")
    p.add_argument("--output", default="reports/tep_nexus_opcua_fault_experiment.json")
    a = p.parse_args()
    if a.endpoint.startswith("opc.tcp://0.0.0.0"):
        p.error("Use a reachable host such as 127.0.0.1, not the server bind address 0.0.0.0")
    if min(a.onset_hours, a.post_window_hours, a.poll_seconds) <= 0 or a.duration_hours < 0:
        p.error("Onset, post-window and polling must be positive; duration nonnegative")
    fault_id = a.fault_id or "paper-opcua-" + uuid4().hex[:12]
    report = asyncio.run(execute(a.endpoint, fault_id, a.fault_type, a.target,
                                 a.magnitude, a.duration_hours, a.onset_hours,
                                 a.post_window_hours, a.poll_seconds,
                                 a.start, a.stop, a.reset))
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"OPC UA experiment recorded: {output}")
    print("Note: TimescaleDB run identity is not established by this script.")


if __name__ == "__main__":
    main()
