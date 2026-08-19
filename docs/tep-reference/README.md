# Tennessee Eastman Process Reference

This document is the technical reference for the TEP backend used by `process-sim`.

The ProfBraatz implementation is treated as the **scientific/reference baseline**. `process-sim` does not reimplement the TEP process equations; it wraps the existing simulator through `TEPAdapter` and builds platform capabilities around it.

## Current status

**Phase 1 foundation is implemented and integrated into the current platform.**

The repository now has:

- a backend-independent simulator boundary
- a TEP adapter around the ProfBraatz `tep` package
- deterministic seeded simulation support
- raw XMEAS/XMV/IDV access
- engineering mappings
- authoritative measurement units for XMEAS1–XMEAS41
- OPC UA integration as a separate protocol boundary
- canonical observation/event recording
- Parquet persistence for recorded runs

The remaining TEP-reference work is primarily deeper numerical validation, reproducibility tooling, and documenting the boundary between the scientific reference and higher-level orchestration.

## 1. Reference source

Primary reference repository:

- https://github.com/camaramm/tennessee-eastman-profBraatz

Public fork reviewed as a secondary copy/reference:

- https://github.com/jkitchin/tennessee-eastman-profbraatz

`process-sim` does **not** depend on `tep-studio` and does not use it as a reference.

The reference repository contains three important Fortran programs/files:

| File | Role |
|---|---|
| `teprob.f` | Core TEP process equations, initialization, process utilities, measurements and disturbance handling |
| `temain.f` | Original/open-loop demonstration program with a simple controller example and Euler integrator |
| `temain_mod.f` | Modified closed-loop plant-wide control demonstration with multiple controllers and fault/disturbance experiments |

Historical training/testing datasets such as `d00.dat` through `d21.dat` and corresponding `_te` files are useful reference material but must not be assumed to represent the complete live simulator interface.

## 2. Reference model dimensions

The reference process model declares:

- **50 differential states**
- state vector `YY(1..50)`
- derivative vector `YP(1..50)`
- simulation time in **hours** inside the Fortran process routines
- **41 XMEAS measurements**
- **12 XMV manipulated variables**
- **20 IDV disturbance slots**

The core process evaluator is:

```fortran
CALL TEFUNC(NN,TIME,YY,YP)
```

Initialization is performed through:

```fortran
CALL TEINIT(NN,TIME,YY,YP)
```

`process-sim` preserves these scientific dimensions at the adapter boundary.

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

The model interface exposes all 12 variables even though historical dataset descriptions sometimes contain only 11 XMV columns.

### Historical dataset discrepancy

Some historical documentation describes an observation vector as:

```text
41 XMEAS + 11 XMV = 52 columns
```

The live model declares and uses **12 XMV variables**. `process-sim` therefore distinguishes:

- **live model interface:** 41 XMEAS + 12 XMV
- **historical ML dataset schema:** 41 XMEAS + 11 XMV where applicable

The missing historical XMV must not be silently treated as absent from the scientific model.

## 4. Process measurements — XMEAS

The 41 measurements are mapped in `src/process_sim/backends/tep/mapping.py`.

### Continuous measurements

| Index | Description | Unit |
|---:|---|---|
| XMEAS1 | A feed, stream 1 | kscmh |
| XMEAS2 | D feed, stream 2 | kg/hr |
| XMEAS3 | E feed, stream 3 | kg/hr |
| XMEAS4 | A and C feed, stream 4 | kscmh |
| XMEAS5 | Recycle flow, stream 8 | kscmh |
| XMEAS6 | Reactor feed rate, stream 6 | kscmh |
| XMEAS7 | Reactor pressure | kPa gauge |
| XMEAS8 | Reactor level | % |
| XMEAS9 | Reactor temperature | deg C |
| XMEAS10 | Purge rate, stream 9 | kscmh |
| XMEAS11 | Product separator temperature | deg C |
| XMEAS12 | Product separator level | % |
| XMEAS13 | Product separator pressure | kPa gauge |
| XMEAS14 | Product separator underflow, stream 10 | m3/hr |
| XMEAS15 | Stripper level | % |
| XMEAS16 | Stripper pressure | kPa gauge |
| XMEAS17 | Stripper underflow, stream 11 | m3/hr |
| XMEAS18 | Stripper temperature | deg C |
| XMEAS19 | Stripper steam flow | kg/hr |
| XMEAS20 | Compressor work | kW |
| XMEAS21 | Reactor cooling-water outlet temperature | deg C |
| XMEAS22 | Separator cooling-water outlet temperature | deg C |

### Sampled composition measurements

**Reactor feed analysis, stream 6**

- XMEAS23–XMEAS28: components A–F
- unit: mol%
- sampling frequency: 0.1 hr
- dead time: 0.1 hr

**Purge gas analysis, stream 9**

- XMEAS29–XMEAS36: components A–H
- unit: mol%
- sampling frequency: 0.1 hr
- dead time: 0.1 hr

**Product analysis, stream 11**

- XMEAS37–XMEAS41: components D–H
- unit: mol%
- sampling frequency: 0.25 hr
- dead time: 0.25 hr

These units are now part of the platform-facing TEP measurement mapping and are propagated into recorded `Observation` records.

XMV units are intentionally not asserted here unless supported by an authoritative reference source.

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

### Disturbance-count discrepancy

`temain_mod.f` mentions **21 programmed disturbances**, while the visible `IDV` common block and core process source expose `IDV(1..20)`.

`process-sim` therefore exposes **20 IDV slots** and does not invent an IDV21 interface. Resolving the historical discrepancy remains a reference-data investigation item.

## 6. Simulation time and integration

The reference examples use:

```fortran
DELTAT = 1. / 3600.
```

This represents a **1-second integration step expressed in hours**.

The original example performs an Euler-style update:

```text
TEFUNC -> derivative
TIME = TIME + DELTAT
YY = YY + YP * DELTAT
```

The modified closed-loop example also uses 1-second increments.

The current ProfBraatz Python simulator exposes this native stepping behavior directly. `TEPAdapter` translates the package API into the `process-sim` simulator boundary rather than rewriting the equations.

The platform keeps **simulation time in hours at the TEP boundary** because that matches the reference model. Higher-level platform APIs may later expose explicit seconds or another canonical time representation where useful.

## 7. Open-loop vs closed-loop reference

### `temain.f`

Useful for understanding the simplest model execution path:

```text
TEINIT
  |
  v
controller example
  |
  v
TEFUNC
  |
  v
Euler integration
```

It contains a simple example PI controller and demonstrates direct manipulated-variable changes.

### `temain_mod.f`

This is the more relevant reference executable for plant-wide closed-loop behavior. It contains controller parameter blocks, setpoints, manipulated-variable initialization, disturbance flags, output generation, and measurement randomness/noise handling.

It remains a **scientific/reference executable**, not the definition of the `process-sim` platform API.

## 8. Controller boundary

The TEP reference contains multiple controller structures. `process-sim` intentionally keeps controller orchestration above the minimum process-model interface.

```text
Process model
    |
    +-- measurements
    +-- manipulated variables
    +-- disturbances
    +-- state/reset
```

Controllers may later be supplied by:

- reference controllers
- Python control logic
- OPC UA clients
- SCADA logic
- MPC/optimization services
- AI agents

This separation is important for the Industrial Twin Core and fault/scenario architecture.

## 9. Current process-sim execution model

```text
                  +------------------+
                  |  TEP reference   |
                  | ProfBraatz/tep   |
                  +--------+---------+
                           |
                     TEPAdapter
                           |
                           v
                  +------------------+
                  | ProcessSimulator |
                  +--------+---------+
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          Recorder       OPC UA       future DWSIM
             |
        Parquet / TSDB
```

The adapter is responsible for translation and platform integration, not scientific reinterpretation.

## 10. Current Python boundary

The current generic protocol is intentionally small and backend-independent:

```python
class ProcessSimulator:
    def reset(self) -> None:
        ...

    def step(self, n_steps: int = 1) -> bool:
        ...

    def get_time_hours(self) -> float:
        ...

    def get_measurements(self):
        ...

    def get_manipulated_variables(self):
        ...

    def set_manipulated_variable(self, index: int, value: float) -> None:
        ...
```

TEP-specific capabilities such as states and IDV manipulation remain behind the TEP adapter.

## 11. Mapping strategy

Two naming layers are maintained.

### Raw/reference names

```text
XMEAS1 ... XMEAS41
XMV1   ... XMV12
IDV1   ... IDV20
```

### Engineering names

Examples include:

```text
XMEAS9  -> reactor_temperature
XMEAS7  -> reactor_pressure
XMEAS8  -> reactor_level
XMV10   -> reactor_cooling_water_flow
```

Raw names remain available for scientific validation. Engineering names and units form the beginning of the platform semantic layer and can later feed the Industrial Knowledge Graph and OPC UA metadata.

## 12. Validation strategy

The original plan was to compare `TEPSimulator` and `TEPAdapter` numerically. Because the adapter is intentionally a thin wrapper around the same ProfBraatz implementation, such a comparison is largely tautological at this stage.

Therefore the current validation strategy is:

### Interface validation

Confirm that the adapter can:

- initialize/reset the model
- advance native simulation steps
- read 41 measurements
- read 12 manipulated variables
- preserve ordering
- report simulation time
- manipulate documented IDV slots

### Scientific/reference validation

Treat the ProfBraatz implementation as the reference scientific baseline. A separate regression dataset becomes valuable once `process-sim` adds orchestration, clocking, fault injection, transformations, or other behavior that could diverge from the backend.

### Dataset validation

Keep the historical 52-column versus live 53-variable distinction explicit:

```text
live snapshot = 41 XMEAS + 12 XMV = 53 variables
historical dataset described in some sources = 41 XMEAS + 11 XMV = 52 columns
```

Do not silently discard XMV12.

## 13. Reproducibility

Simulation runs should record enough information to reproduce an experiment:

```text
SimulationRun
  +-- run_id
  +-- backend
  +-- backend/version information
  +-- random_seed
  +-- initial conditions
  +-- input configuration
  +-- disturbance configuration
  +-- native timestep
  +-- duration
```

The recording foundation already persists `run_id` and run metadata. Future scenario manifests and lifecycle events will extend this provenance model.

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
- adding AI before the semantic and temporal foundations are sufficiently stable

## 15. Relationship to the roadmap

The TEP reference work is the foundation of **Phase 1 — TEP Reference and Python Simulation Integration**.

The next major platform capabilities are:

1. **Phase 2 — Industrial Twin Core:** canonical assets, identity, orchestration, lifecycle, states, and source-generated events.
2. **Phase 3 — Fault Injection and Scenario Engineering:** first-class faults, scenarios, and fault events.
3. **Phase 5 — Time-Series and Temporal Knowledge Infrastructure:** the recording foundation is already started; next steps are lifecycle events, production time-series evaluation, and Temporal KG modeling.

OPC UA is already implemented as the initial **Phase 4** integration layer and will continue to mature independently through semantic metadata, subscriptions, hierarchy, and fault/event integration.

## 16. Related documentation

- `docs/tep-reference/USAGE.md` — practical TEP adapter usage
- `docs/opcua/README.md` — current OPC UA architecture and roadmap
- root `README.md` — overall project status, architecture, recording workflow, and ten-phase roadmap
