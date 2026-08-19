# Tennessee Eastman Process Reference

This document is the technical reference for the TEP backend used by `process-sim`.

The ProfBraatz implementation is treated as the **scientific/reference baseline**. `process-sim` does not reimplement the TEP process equations; it wraps the existing simulator through `TEPAdapter` and builds platform capabilities around it.

## Current status

**Phase 1 foundation is implemented; fault/scenario integration is now underway.**

The repository currently has:

- a backend-independent simulator boundary
- a TEP adapter around the ProfBraatz `tep` package
- deterministic seeded simulation support
- raw XMEAS/XMV/IDV access
- engineering mappings
- authoritative measurement units for XMEAS1–XMEAS41
- OPC UA integration as a separate protocol boundary
- canonical observation/event recording
- run manifests and provenance metadata
- Parquet persistence for recorded runs
- a first-class FaultManager supporting bias, drift, stuck, and process-disturbance fault types
- fault activation/deactivation events routed into the canonical recording model

The remaining TEP-reference work is primarily deeper numerical validation, reproducibility tooling, and integrating process-disturbance faults with the native TEP IDV interface.

## 1. Reference source

Primary reference repository:

- https://github.com/camaramm/tennessee-eastman-profBraatz

Public fork reviewed as a secondary copy/reference:

- https://github.com/jkitchin/tennessee-eastman-profbraatz

`process-sim` does not reimplement the scientific model. The adapter remains the platform boundary around the reference package.

## 2. Reference model dimensions

The reference process model declares:

- **50 differential states**
- state vector `YY(1..50)`
- derivative vector `YP(1..50)`
- simulation time in **hours** inside the Fortran process routines
- **41 XMEAS measurements**
- **12 XMV manipulated variables**
- **20 IDV disturbance slots**

The core process evaluator is `TEFUNC`; initialization is performed through `TEINIT`. `process-sim` preserves these scientific dimensions at the adapter boundary.

## 3. Manipulated variables — XMV

| Index | Meaning |
|---:|---|
| XMV1 | D feed flow, stream 2 |
| XMV2 | E feed flow, stream 3 |
| XMV3 | A feed flow, stream 1 |
| XMV4 | A and C feed flow, stream 4 |
| XMV5 | Compressor recycle valve |
| XMV6 | Purge valve, stream 9 |
| XMV7 | Separator pot liquid flow, stream 10 |
| XMV8 | Stripper liquid product flow, stream 11 |
| XMV9 | Stripper steam valve |
| XMV10 | Reactor cooling-water flow |
| XMV11 | Condenser cooling-water flow |
| XMV12 | Agitator speed |

The live model exposes all 12 variables even though historical datasets sometimes contain only 11 XMV columns.

## 4. Process measurements — XMEAS

The 41 measurements are mapped in `src/process_sim/backends/tep/mapping.py`.

XMEAS1–XMEAS22 are continuous process measurements. XMEAS23–XMEAS28 are reactor-feed composition measurements, XMEAS29–XMEAS36 are purge-gas composition measurements, and XMEAS37–XMEAS41 are product composition measurements. The platform mapping contains authoritative units for all 41 measurements and propagates them into recorded `Observation` records.

XMV units remain unset until a sufficiently authoritative source is identified rather than inventing engineering units.

## 5. Disturbances — IDV

The core source declares `IDV(1..20)`.

| IDV | Description | Category |
|---:|---|---|
| 1 | A/C feed ratio, B composition constant, stream 4 | Step |
| 2 | B composition, A/C ratio constant, stream 4 | Step |
| 3 | D feed temperature, stream 2 | Step |
| 4 | Reactor cooling-water inlet temperature | Step |
| 5 | Condenser cooling-water inlet temperature | Step |
| 6 | A feed loss, stream 1 | Step |
| 7 | C header pressure loss / reduced availability, stream 4 | Step |
| 8 | A/B/C feed composition, stream 4 | Random variation |
| 9 | D feed temperature, stream 2 | Random variation |
| 10 | C feed temperature, stream 4 | Random variation |
| 11 | Reactor cooling-water inlet temperature | Random variation |
| 12 | Condenser cooling-water inlet temperature | Random variation |
| 13 | Reaction kinetics | Slow drift |
| 14 | Reactor cooling-water valve | Sticking |
| 15 | Condenser cooling-water valve | Sticking |
| 16 | Not documented in source | Unknown |
| 17 | Not documented in source | Unknown |
| 18 | Not documented in source | Unknown |
| 19 | Not documented in source | Unknown |
| 20 | Not documented in source | Unknown |

`process-sim` exposes 20 IDV slots and does not invent an IDV21 interface. The historical discrepancy between a comment mentioning 21 disturbances and the visible `IDV(1..20)` declaration remains a reference-data investigation item.

## 6. Simulation time and integration

The reference examples use `DELTAT = 1. / 3600.`, representing a **1-second integration step expressed in hours**. `TEPAdapter` preserves this native stepping behavior rather than rewriting the equations.

## 7. Fault injection boundary

Fault injection now sits around the scientific reference model rather than inside its equations:

```text
                 TEP reference model
                        │
                    TEPAdapter
                        │
                 FaultManager
                  /     |      \
               XMEAS   XMV     IDV
                 │      │       │
              sensor  actuator process
               faults  faults  disturbances
```

Current signal-level mechanisms:

- **bias** — additive offset
- **drift** — time-dependent additive change
- **stuck** — forces a configured signal value
- **process disturbance** — first-class scheduled fault, intentionally not yet applied as a generic signal transformation

Fault lifecycle events currently include:

- `FaultActivated`
- `FaultDeactivated`

These events can be passed to `SimulationRecordingSession.record_fault_event()` and persisted with the run's other events.

The architectural boundary is deliberate: sensor and actuator faults can be represented as signal transformations, while process disturbances must eventually enter through the TEP model's native IDV mechanism.

## 8. Current execution model

```text
                  +------------------+
                  |  TEP reference   |
                  | ProfBraatz/tep   |
                  +--------+---------+
                           |
                     TEPAdapter
                           |
                 +---------+---------+
                 |                   |
           FaultManager          Recorder
                 |                   |
          XMEAS / XMV          Parquet / future TSDB
                 |
          Fault lifecycle events
```

The adapter remains responsible for translation and platform integration, not scientific reinterpretation.

## 9. Run provenance

Recorded runs now have a `RunManifest` containing run identity and provenance such as:

```text
run_id
simulator
backend
random_seed
real_time_factor
scenario
started_at
completed_at
metadata
```

This is the foundation for reproducible fault/scenario experiments. Future manifests will add richer scenario definitions, initial conditions, and configuration fingerprints.

## 10. Controller boundary

Controllers remain above the minimum process-model interface. They may later be supplied by reference controllers, Python control logic, OPC UA clients, SCADA logic, MPC/optimization services, or AI agents.

This separation is important for the Industrial Twin Core and fault/scenario architecture.

## 11. Mapping strategy

Raw/reference names remain stable:

```text
XMEAS1 ... XMEAS41
XMV1   ... XMV12
IDV1   ... IDV20
```

Engineering names can be layered on top, for example:

```text
XMEAS9  -> reactor_temperature
XMEAS7  -> reactor_pressure
XMEAS8  -> reactor_level
XMV10   -> reactor_cooling_water_flow
```

Raw names remain available for scientific validation; engineering names and units form the beginning of the platform semantic layer.

## 12. Validation strategy

Comparing `TEPSimulator` and `TEPAdapter` numerically is largely tautological because the adapter is intentionally a thin wrapper around the same ProfBraatz implementation.

Current validation therefore emphasizes interface integrity, reference-model behavior, deterministic seeds, measurement ordering, and explicit live-versus-historical dataset differences. A separate numerical regression dataset becomes more valuable once `process-sim` adds transformations, orchestration, and fault injection that can diverge from the backend.

## 13. Reproducibility

A reproducible experiment should capture:

```text
SimulationRun
  +-- run_id
  +-- backend
  +-- random_seed
  +-- initial conditions
  +-- scenario
  +-- fault configuration
  +-- native timestep
  +-- duration
  +-- recording configuration
```

The current run manifest and event log provide the first implementation of this provenance model.

## 14. What we should NOT do

The project should continue to avoid:

- translating all 50 process equations into Python
- changing scientific equations for convenience
- putting OPC UA calls inside process equations
- putting GraphDB calls inside the simulation timestep
- treating GraphDB as a high-frequency historian
- inventing missing disturbance definitions
- assuming historical dataset columns equal the complete live process interface
- coupling recording to OPC UA client polling
- applying process disturbances as arbitrary signal transformations
- adding AI before the semantic and temporal foundations are sufficiently stable

## 15. Relationship to the roadmap

The TEP reference remains the foundation of **Phase 1 — TEP Reference and Python Simulation Integration**.

The major active platform layers are now:

1. **Phase 2 — Industrial Twin Core:** canonical assets, identity, orchestration, lifecycle, states, and source-generated events.
2. **Phase 3 — Fault Injection and Scenario Engineering:** the first FaultManager layer is implemented; scenario definitions and native IDV integration remain next.
3. **Phase 4 — OPC UA Integration:** initial implementation is complete and operator event integration is underway.
4. **Phase 5 — Time-Series and Temporal Knowledge Infrastructure:** recording, units, events, Parquet persistence, and run provenance are implemented; production TSDB and Temporal KG work remains.

These phases are architectural milestones, not a strict sequential implementation order.

## 16. Related documentation

- `docs/tep-reference/USAGE.md` — practical TEP adapter usage
- `docs/opcua/README.md` — current OPC UA architecture and roadmap
- root `README.md` — overall project status and ten-phase roadmap
