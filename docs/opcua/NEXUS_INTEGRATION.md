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
