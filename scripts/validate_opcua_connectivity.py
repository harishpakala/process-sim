#!/usr/bin/env python3
"""Validate standalone OPC UA Connectivity AAS references and signal IDs."""

# Created: 2026-10-22
# Author: Harish
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
load = lambda path: json.loads((root / path).read_text(encoding="utf-8"))
model = load("examples/aas/tep_opcua_connectivity_instance.json")
dexpi = load("examples/aas/tep_dexpi_instance.json")
functions = {next(p["value"] for p in f["value"] if p["idShort"] == "AssetIdentifier")
             for group in dexpi["submodelElements"] if group["idShort"] in ("InstrumentationFunctions", "ActuatingFunctions")
             for f in group["value"]}
groups = {g["idShort"]: g for g in model["submodelElements"]}
servers = groups["Servers"]["value"]
assert len(servers) == 1
server = {p["idShort"]: p["value"] for p in servers[0]["value"]}
assert server["NamespaceURI"] == "urn:process-sim:opcua"
assert server["ECADConnectionPointReferenceStatus"] == "UNMAPPED_NO_VERIFIED_INTERFACE"
records = groups["SignalMappings"]["value"]
assert len(records) == 34, len(records)
seen_functions, seen_signals = set(), set()
for item in records:
    props = {p["idShort"]: p["value"] for p in item["value"]}
    function, signal = props["EngineeringFunctionReference"], props["SignalName"]
    assert function in functions, function
    assert function not in seen_functions and signal not in seen_signals
    seen_functions.add(function)
    seen_signals.add(signal)
    if signal.startswith("XMEAS"):
        assert 1 <= int(signal[5:]) <= 41 and props["SignalDirection"] == "READ"
        folder = "Measurements"
    else:
        assert signal.startswith("XMV") and 1 <= int(signal[3:]) <= 12
        assert props["SignalDirection"] == "READ_WRITE"
        folder = "ManipulatedVariables"
    assert props["OPCUANodeId"] == f"nsu=urn:process-sim:opcua;s=TEP.{folder}.{signal}"
    assert props["MappingStatus"] == "PROVISIONAL_ENGINEERING_MATCH"
print("PASS: 34 unique DEXPI references and OPC UA signal mappings in separate AAS submodel")
