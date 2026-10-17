# TEP NEXUS OPC UA integration (initial)

The existing OPC UA server remains the sole operational boundary for the TEP
simulator. The Python HTTP API uses an `asyncua` client; the browser does not
connect to OPC UA directly.

## Start locally

Install the OPC UA dependency and the ProfBraatz `tep` package as described
in the repository setup. From the repository root:

```bash
pip install -r requirements-opcua.txt
```

Start three separate terminals:

```bash
# Terminal 1 — existing TEP OPC UA server
PYTHONPATH=src python examples/run_opcua_server.py

# Terminal 2 — Python HTTP API (GraphDB and OPC UA bridge)
PYTHONPATH=src python -m process_sim.api.server

# Terminal 3 — Vue
cd frontend && npm run dev
```

On Windows PowerShell, run `$env:PYTHONPATH="src"` in each Python terminal
before its command.

Open **Simulation > Simulation Control** in TEP NEXUS. The page polls
`GET /api/simulation/status` every two seconds and sends lifecycle commands
to `POST /api/simulation/control` with
`{"action":"Start"|"Stop"|"Reset"}`.

The OPC UA URL defaults to `opc.tcp://127.0.0.1:4841/process-sim/`.
Override it using `TEP_OPCUA_ENDPOINT` in the Python API environment.

## Scope and safety

This first integration reads 41 XMEAS and 12 XMV values and supports
Start/Stop/Reset. XMV writes, faults, subscriptions, and historian/trends
are not yet exposed in the UI. The existing OPC UA launcher uses **manual**
control mode, so process control is not supplied by the native closed-loop
controller. Use in a local simulation environment only.

The Python API is a development bridge and has no authentication. Keep it
bound to loopback and do not expose operator methods to untrusted networks.
This integration has not been verified against a running OPC UA server in
the user's environment.

## Fault injection and management

Open **Simulation > Faults & Disturbances**. The UI calls the Python API,
which forwards operations to the existing OPC UA `TEP/FaultManagement` methods:

| HTTP endpoint | OPC UA method |
| --- | --- |
| `GET /api/simulation/faults` | `ListFaults()` |
| `POST /api/simulation/faults` with `{"action":"inject",...}` | `InjectFault(...)` |
| `POST /api/simulation/faults` with `{"action":"clear","faultId":"..."}` | `ClearFault(...)` |
| `POST /api/simulation/faults` with `{"action":"clear_all"}` | `ClearAllFaults()` |

Example injection payload:

```json
{"action":"inject","faultId":"trial-1","faultType":"process_disturbance","target":"IDV1","magnitude":1.0,"value":0.0,"durationHours":0.5}
```

Fault types: `process_disturbance` (IDV1–IDV20), `bias`,
`drift`, and `stuck` (XMEAS1–XMEAS41 or XMV1–XMV12).
Duration zero means indefinite. The UI polls the fault list every
four seconds and displays active, registered, and expired states as
reported by the OPC UA server.

**Safety:** These are live commands to the simulator. The API is bound
to loopback by default and has no authentication; do not expose it
to an untrusted network. The OPC UA server owns fault lifecycle,
state and validation. No new fault model has been introduced.
