# OPC UA integration

The OPC UA layer is an asynchronous integration boundary around the simulator. It does not contain TEP process physics and it does not own the deterministic process model.

## Status

**Initial OPC UA integration is implemented.**

The current implementation provides:

- stable application namespace: `urn:process-sim:opcua`
- `TEP` object
- simulation time and running state
- configurable real-time factor
- `Start()`, `Stop()`, and `Reset()` methods
- 41 raw XMEAS variables
- 12 raw XMV variables
- explicit OPC UA writes for XMV values
- asynchronous simulation loop

The development endpoint currently uses port **4841** because port 4840 was occupied in the development environment:

```text
opc.tcp://0.0.0.0:4841/process-sim/
```

## Current namespace

```text
Objects
└── TEP
    ├── Simulation
    │   ├── TimeHours
    │   ├── Running
    │   ├── RealTimeFactor
    │   ├── Start()
    │   ├── Stop()
    │   └── Reset()
    ├── Measurements
    │   └── XMEAS1 ... XMEAS41
    └── ManipulatedVariables
        └── XMV1 ... XMV12
```

Raw XMEAS/XMV identifiers are intentionally retained because they provide a stable bridge to the TEP reference model. Semantic engineering names and richer OPC UA metadata will be layered on top rather than replacing the raw interface.

## Architecture

```text
                    process-sim
                         │
              ┌──────────┴──────────┐
              │                     │
        TEPAdapter              OPC UA Server
              │                     │
              ▼                     ▼
       TEP simulation          SCADA / HMI / clients
              │
              └──── deterministic simulation clock
```

OPC UA clients do not synchronously own the simulation timestep. Writes are synchronized explicitly into the simulator, and the simulation loop remains independent of external clients.

## Install

```bash
pip install -r requirements-opcua.txt
```

The transport uses `asyncua`.

## Running the server

The repository includes the OPC UA server entry point under `process_sim.protocols.opcua`.

The server is constructed with a simulator and can be configured with a real-time factor and update interval. A real-time factor of `1.0` corresponds to approximately real-time execution for the 1-second native TEP step.

A minimal integration pattern is:

```python
import asyncio

from process_sim.backends.tep import TEPAdapter
from process_sim.protocols.opcua import OPCUAServer


async def main():
    simulator = TEPAdapter(random_seed=123)
    simulator.reset()

    server = OPCUAServer(
        simulator,
        endpoint="opc.tcp://0.0.0.0:4841/process-sim/",
        namespace_uri="urn:process-sim:opcua",
        real_time_factor=1.0,
        update_interval_seconds=1.0,
    )
    await server.start()

    try:
        await server.start_simulation()
        while True:
            await asyncio.sleep(1.0)
    finally:
        await server.stop()


asyncio.run(main())
```

## Current design boundary

The OPC UA layer is responsible for:

- industrial protocol exposure
- lifecycle methods
- simulation status publication
- reading operator/client XMV writes
- publishing current XMEAS/XMV values

It is **not** responsible for:

- TEP process equations
- scientific model validation
- persistent historical storage
- GraphDB transactions in the simulation timestep
- long-term event inference

Recording is a separate subsystem and samples the simulator directly rather than polling OPC UA.

## Units and semantic metadata

The TEP reference mapping now contains authoritative engineering units for all 41 XMEAS measurements. The recording layer uses those units when creating canonical observations.

The OPC UA namespace still exposes raw XMEAS/XMV variables. The next metadata step is to expose engineering names and units through OPC UA metadata, ideally using standard OPC UA engineering-unit conventions such as `EUInformation` where appropriate.

XMV units are intentionally not invented until a sufficiently authoritative reference is available.

## Roadmap

### Completed

- stable namespace
- raw XMEAS/XMV nodes
- simulation time/running state
- Start/Stop/Reset lifecycle
- real-time-factor control
- explicit XMV write synchronization
- asynchronous simulation loop

### Next OPC UA work

1. **Semantic node metadata** — engineering names, descriptions, units, and standard engineering-unit metadata.
2. **Quality and timestamps** — expose OPC UA status/quality and simulation versus wall-clock timestamps where appropriate.
3. **Subscriptions and client integration tests** — verify monitored-item behavior and write/read semantics with an OPC UA client.
4. **Process/equipment hierarchy** — organize reactor, separator, stripper, compressor, utilities, instruments, and tags without removing the raw XMEAS/XMV layer.
5. **Fault/scenario controls** — integrate with the planned Phase 3 FaultManager using explicit methods/events rather than embedding fault logic in the protocol adapter.
6. **Operational events** — connect operator actions and communication/data-quality events to the canonical event recorder.

## Relationship to the project roadmap

OPC UA corresponds to **Phase 4 — OPC UA Integration** in the root project roadmap. The initial implementation is complete; the remaining work is semantic enrichment, interoperability testing, hierarchy, and integration with the broader event/fault architecture.

Phase 5 recording is intentionally independent of OPC UA. This prevents the historian/temporal-data path from becoming coupled to a particular client protocol.
