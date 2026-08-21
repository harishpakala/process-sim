# OPC UA integration

The OPC UA layer is an asynchronous integration boundary around the simulator. It does not contain TEP process physics and it does not own the deterministic process model.

## Status

**Initial OPC UA integration and the first operator fault-management contract are implemented.**

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
- explicit OPC UA fault-management methods
- operator fault provenance and lifecycle callbacks

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
    ├── FaultManagement
    │   ├── FaultCount
    │   ├── InjectFault(...)
    │   ├── ClearFault(faultId)
    │   ├── ClearAllFaults()
    │   └── ListFaults()
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
              │                     │
       ┌──────┴──────┐              │ OPC UA commands
       │             │              │
 FaultManager     Recorder ◄────────┘
       │             │
       └──────┬──────┘
              ▼
       fault/event history
```

The OPC UA boundary is the intended operational interface for a future SCADA/HMI. The HMI should not call simulator internals directly. Fault commands cross the OPC UA boundary, enter the canonical `FaultManager`, and are then applied by the simulator adapter at the process boundary.

## Install

```bash
pip install -r requirements-opcua.txt
```

The transport uses `asyncua`.

## Running the server

The repository includes the OPC UA server entry point under `process_sim.protocols.opcua`.

The server is constructed with a simulator and can be configured with a real-time factor and update interval. A real-time factor of `1.0` corresponds to approximately real-time execution for the 1-second native TEP step.

## Fault-management contract

The operational fault boundary is intentionally explicit rather than exposing Python objects or simulator internals to OPC UA clients.

### InjectFault

```text
InjectFault(
    faultId,
    faultType,
    target,
    magnitude,
    value,
    durationHours
)
```

Semantics:

- `faultId` uniquely identifies the operator fault.
- `faultType` is one of `bias`, `drift`, `stuck`, or `process_disturbance`.
- `target` identifies the signal or process disturbance, such as `XMEAS9` or `IDV6`.
- `magnitude` is used by bias, drift, and process-disturbance faults.
- `value` is used by stuck faults.
- `durationHours == 0` means the fault remains active until explicitly cleared.
- a positive duration starts at the current simulation-time boundary.
- operator injection is tagged with `injection_source=opcua` and `operator_injected=true`.

### ClearFault / ClearAllFaults

`ClearFault(faultId)` removes a configured fault immediately and emits a `FaultCleared` provenance event. `ClearAllFaults()` performs the same operation for every configured fault.

Scheduled lifecycle transitions remain distinct:

```text
FaultInjected
      ↓
FaultActivated
      ↓
FaultDeactivated
```

An operator clearing a fault before its scheduled end is represented explicitly as:

```text
FaultInjected
      ↓
FaultCleared
```

This distinction preserves the difference between an experiment-defined lifecycle and an operator intervention.

### ListFaults / FaultCount

`ListFaults()` returns the configured fault set as JSON for diagnostics and HMI integration. `FaultCount` provides a simple read-only count for clients.

### Process disturbances

Process-disturbance faults are mapped to the native TEP IDV interface. The OPC UA contract accepts `IDV1` through `IDV20` and records the resolved `idv_index` in fault metadata. The fault is not applied as a generic measurement transformation.

## Recording and provenance

Fault lifecycle and operator events remain independent of OPC UA. The server exposes callback hooks so a recording session can route them into canonical events without making the recorder depend on the protocol implementation.

This preserves the intended separation:

```text
SCADA / HMI
     │ OPC UA
     ▼
FaultManagement
     ▼
FaultManager
     ▼
TEPAdapter
     ├── measurements
     ├── controller input path
     ├── process disturbances
     └── event/provenance sink
```

The declarative YAML/JSON scenario path remains the authoritative path for reproducible benchmark design. OPC UA fault injection is the operator-facing operational path.

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
- first OPC UA fault-management contract
- operator fault injection/clear operations
- process-disturbance mapping to TEP IDVs
- fault provenance callback integration

### Next OPC UA work

1. **Semantic node metadata** — engineering names, descriptions, units, and standard engineering-unit metadata.
2. **Quality and timestamps** — expose OPC UA status/quality and simulation versus wall-clock timestamps where appropriate.
3. **Subscriptions and client integration tests** — verify monitored-item behavior and write/read semantics with an OPC UA client.
4. **Process/equipment hierarchy** — organize reactor, separator, stripper, compressor, utilities, instruments, and tags without removing the raw XMEAS/XMV layer.
5. **SCADA/HMI integration** — build the operator interface entirely through the OPC UA contract.
6. **Security and deployment configuration** — move beyond the development endpoint and define authentication, certificates, endpoint policy, and deployment configuration.

## Relationship to the project roadmap

OPC UA corresponds to **Phase 4 — OPC UA Integration**. The initial operational contract is now implemented; the remaining work is semantic enrichment, interoperability testing, hierarchy, SCADA/HMI integration, and deployment/security hardening.

Phase 5 recording remains independent of OPC UA. This prevents the historian/temporal-data path from becoming coupled to a particular client protocol.
