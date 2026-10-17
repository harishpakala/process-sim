"""OPC UA client boundary for the TEP NEXUS HTTP API."""
from __future__ import annotations

import os

ENDPOINT = os.environ.get("TEP_OPCUA_ENDPOINT", "opc.tcp://127.0.0.1:4841/process-sim/")


async def _node(parent, name: str):
    children = await parent.get_children()
    for child in children:
        if (await child.read_browse_name()).Name == name:
            return child
    raise LookupError(f"OPC UA node not found: {name}")


async def snapshot():
    from asyncua import Client

    async with Client(ENDPOINT, timeout=5) as client:
        tep = await _node(client.nodes.objects, "TEP")
        sim = await _node(tep, "Simulation")
        measurements = await _node(tep, "Measurements")
        mvs = await _node(tep, "ManipulatedVariables")
        state = {}
        for name in ("TimeHours", "Running", "ControlMode", "RealTimeFactor"):
            state[name] = await (await _node(sim, name)).read_value()
        xmeas = [float(await (await _node(measurements, f"XMEAS{i}")).read_value()) for i in range(1, 42)]
        xmv = [float(await (await _node(mvs, f"XMV{i}")).read_value()) for i in range(1, 13)]
        return {"connected": True, "simulation": state, "measurements": xmeas, "manipulatedVariables": xmv}


async def control(action: str):
    if action not in {"Start", "Stop", "Reset"}:
        raise ValueError("Unsupported simulation action")
    from asyncua import Client

    async with Client(ENDPOINT, timeout=5) as client:
        tep = await _node(client.nodes.objects, "TEP")
        sim = await _node(tep, "Simulation")
        method = await _node(sim, action)
        result = await sim.call_method(method)
        return {"action": action, "success": bool(result)}
