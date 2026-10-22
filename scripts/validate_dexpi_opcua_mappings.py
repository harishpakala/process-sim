#!/usr/bin/env python3
"""Validate DEXPI function-to-OPC-UA signal mappings without a running server."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "examples/aas/tep_dexpi_instance.json").read_text(encoding="utf-8"))
groups = {x["idShort"]: x["value"] for x in data["submodelElements"]}
expected = {"InstrumentationFunctions": (22, "XMEAS", 41, "MeasuredVariable", "Measurements", "READ"),
            "ActuatingFunctions": (12, "XMV", 12, "ActuatedVariable", "ManipulatedVariables", "READ_WRITE")}
seen = set()
for name, (count, prefix, maximum, field, folder, direction) in expected.items():
    records = groups[name]
    assert len(records) == count, (name, len(records))
    for record in records:
        props = {p["idShort"]: p["value"] for p in record["value"] if p["modelType"] == "Property"}
        signal = props[field]
        assert signal.startswith(prefix) and signal[len(prefix):].isdigit(), record["idShort"]
        assert 1 <= int(signal[len(prefix):]) <= maximum
        assert signal not in seen, signal
        seen.add(signal)
        assert props["OPCUANamespaceURI"] == "urn:process-sim:opcua"
        assert props["OPCUANodeId"] == f"nsu=urn:process-sim:opcua;s=TEP.{folder}.{signal}"
        assert props["OPCUABrowsePath"] == f"Objects/TEP/{folder}/{signal}"
        assert props["OPCUAMappingStatus"] == "PROVISIONAL_ENGINEERING_MATCH"
        assert props["OPCUASignalDirection"] == direction
print(f"PASS: {len(seen)} unique provisional DEXPI OPC UA function mappings validated")
