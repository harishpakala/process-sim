# OPC UA integration

The OPC UA layer is an asynchronous integration boundary around the simulator. It does not contain TEP process physics and it does not own the deterministic process model.

## Status

**Initial OPC UA integration is implemented and fault/event integration has started.**

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
- operator XMV changes connected to canonical event recording

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
       ┌──────┴──────┐
       │             │
 FaultManager     Recorder
       │             │
       └──────┬──────┘
              ▼
       fault/event history
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

## Fault and event boundary

Fault logic is not embedded in the OPC UA protocol implementation. The current architecture is:

```text
OPC UA client
     │
     │ XMV write
     ▼
 OPC UA adapter
     │
     ▼
 TEPAdapter ◄──── FaultManager
     │                 │
     │                 ├── Bias
     │                 ├── Drift
     │                 ├── Stuck
     │                 └── Process disturbance
     │
     ├── measurements
     └── manipulated variables
```

The `FaultManager` can transform published XMEAS/XMV values and emits lifecycle events through an optional event sink. Current lifecycle events are `FaultActivated` and `FaultDeactivated`.

The initial process-disturbance fault type is deliberately not applied as a generic signal transformation; process disturbances belong at the process-model boundary and will be integrated with TEP IDVs in the next fault/scenario increment.

## Recording integration

Recording remains independent of OPC UA. The live server can connect operator XMV writes to `SimulationRecordingSession`, producing canonical `ManipulatedVariableChanged` events. Fault lifecycle events can likewise be routed through the recording session without making the recorder depend on OPC UA.

## Units and semantic metadata

The TEP reference mapping contains authoritative engineering units for all 41 XMEAS measurements. The recording layer uses those units when creating canonical observations.

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
- operator XMV event integration

### Next OPC UA work

1. **Semantic node metadata** — engineering names, descriptions, units, and standard engineering-unit metadata.
2. **Quality and timestamps** — expose OPC UA status/quality and simulation versus wall-clock timestamps where appropriate.
3. **Subscriptions and client integration tests** — verify monitored-item behavior and write/read semantics with an OPC UA client.
4. **Process/equipment hierarchy** — organize reactor, separator, stripper, compressor, utilities, instruments, and tags without removing the raw XMEAS/XMV layer.
5. **Fault/scenario controls** — expose FaultManager scenarios through explicit methods/events rather than embedding fault logic in the protocol adapter.
6. **Process disturbances** — connect scenario-managed faults to the native TEP IDV interface.

## Relationship to the project roadmap

OPC UA corresponds to **Phase 4 — OPC UA Integration**. The initial implementation is complete; the remaining work is semantic enrichment, interoperability testing, hierarchy, and integration with the broader fault/scenario architecture.

Phase 5 recording is intentionally independent of OPC UA. This prevents the historian/temporal-data path from becoming coupled to a particular client protocol.
