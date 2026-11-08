"""OPC UA client boundary for the TEP NEXUS HTTP API."""

# Created: 2026-10-17
# Author: Harish
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

async def faults_list():
    """Read the existing OPC UA FaultManagement.ListFaults method."""
    import json
    from asyncua import Client
    async with Client(ENDPOINT, timeout=5) as client:
        tep = await _node(client.nodes.objects, "TEP")
        parent = await _node(tep, "FaultManagement")
        method = await _node(parent, "ListFaults")
        raw = await parent.call_method(method)
        faults = json.loads(raw)
        if not isinstance(faults, list):
            raise ValueError("Unexpected ListFaults response")
        return {"faults": faults}


async def fault_command(action: str, payload: dict):
    """Call the server's existing fault methods, without duplicating fault logic."""
    import math
    from asyncua import Client, ua
    method_names = {"inject": "InjectFault", "clear": "ClearFault", "clear_all": "ClearAllFaults"}
    if action not in method_names:
        raise ValueError("Unsupported fault action")
    arguments = []
    if action == "inject":
        fault_id = payload.get("faultId")
        kind = payload.get("faultType")
        target = payload.get("target")
        if not isinstance(fault_id, str) or not 1 <= len(fault_id) <= 100 or not fault_id.strip():
            raise ValueError("A fault ID is required (max 100 characters)")
        if kind not in ("bias", "drift", "stuck", "process_disturbance"):
            raise ValueError("Unsupported fault type")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("A target is required")
        if kind == "process_disturbance":
            if target not in [f"IDV{i}" for i in range(1, 21)]:
                raise ValueError("Process disturbance target must be IDV1..IDV20")
        elif target not in [f"XMEAS{i}" for i in range(1, 42)] + [f"XMV{i}" for i in range(1, 13)]:
            raise ValueError("Invalid sensor or actuator target")
        numeric = []
        for key in ("magnitude", "value", "durationHours"):
            val = payload.get(key, 0)
            if isinstance(val, bool) or not isinstance(val, (float, int)) or not math.isfinite(val):
                raise ValueError(f"{key} must be a finite number")
            numeric.append(float(val))
        if numeric[2] < 0:
            raise ValueError("durationHours must be non-negative")
        arguments = [ua.Variant(fault_id, ua.VariantType.String), ua.Variant(kind, ua.VariantType.String), ua.Variant(target, ua.VariantType.String)]
        arguments.extend(ua.Variant(v, ua.VariantType.Double) for v in numeric)
    elif action == "clear":
        fault_id = payload.get("faultId")
        if not isinstance(fault_id, str) or not fault_id.strip():
            raise ValueError("A fault ID is required")
        arguments = [ua.Variant(fault_id, ua.VariantType.String)]
    async with Client(ENDPOINT, timeout=5) as client:
        tep = await _node(client.nodes.objects, "TEP")
        parent = await _node(tep, "FaultManagement")
        method = await _node(parent, method_names[action])
        result = await parent.call_method(method, *arguments)
        return {"action": action, "success": bool(result)}
