# Tennessee Eastman Process Reference

This document is the working technical specification for **Phase 1** of `process-sim`.

The purpose is to understand the reference Tennessee Eastman Process (TEP) implementation before designing the Python adapter. We intentionally treat the reference implementation as a scientific baseline rather than rewriting its process equations into Python at this stage.

## 1. Reference source

Primary reference repository:

- https://github.com/camaramm/tennessee-eastman-profBraatz

Public fork reviewed as a secondary copy/reference:

- https://github.com/jkitchin/tennessee-eastman-profbraatz

`process-sim` does **not** depend on `tep-studio` and does not use it as a reference.

The upstream repository contains three important Fortran programs/files:

| File | Role |
|---|---|
| `teprob.f` | Core TEP process equations, initialization, process utilities, measurements and disturbance handling |
| `temain.f` | Original/open-loop demonstration program with a simple controller example and Euler integrator |
| `temain_mod.f` | Modified closed-loop plant-wide control demonstration with multiple controllers and fault/disturbance experiments |

The repository also contains historical training/testing datasets such as `d00.dat` through `d21.dat` and corresponding `_te` files.

## 2. What the reference implementation actually contains

### 2.1 Process state

The reference process model declares:

- **50 differential states**
- state vector `YY(1..50)`
- derivative vector `YP(1..50)`
- simulation time in **hours** inside the Fortran process routines

The core process evaluator is:

```fortran
CALL TEFUNC(NN,TIME,YY,YP)
```

Initialization is performed through:

```fortran
CALL TEINIT(NN,TIME,YY,YP)
```

The source documentation explicitly notes that additional states can be appended to the state vector, but `process-sim` should **not** extend the scientific model in Phase 1.

### 2.2 Public process variables

The reference implementation exposes two important common blocks:

```text
XMEAS(1..41)   process measurements
XMV(1..12)     manipulated variables
IDV(1..20)     disturbance flags
```

This gives us the natural first boundary for the Python adapter.

## 3. Manipulated variables — XMV

The reference source defines 12 manipulated variables:

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

The first three feed descriptions are marked in the source as having corrected ordering.

### Important dataset discrepancy

The historical dataset description in the upstream README says that an observation vector contains:

```text
41 XMEAS + 11 XMV = 52 columns
```

However, the Fortran model declares **12 XMV variables**. The closed-loop output program also writes manipulated variables 1 through 12.

Therefore `process-sim` must **not silently assume that the historical 52-column datasets represent all model inputs**. We will explicitly distinguish:

- the model interface: 41 measurements + 12 manipulated variables
- the historical ML dataset schema: 41 measurements + 11 manipulated variables

This is an important validation item for Phase 1.

## 4. Process measurements — XMEAS

### 4.1 Continuous measurements

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

### 4.2 Sampled measurements

The remaining measurements are composition analyses.

**Reactor feed analysis, stream 6**

- XMEAS23: component A
- XMEAS24: component B
- XMEAS25: component C
- XMEAS26: component D
- XMEAS27: component E
- XMEAS28: component F

Sampling frequency: **0.1 hr** with **0.1 hr dead time**.

**Purge gas analysis, stream 9**

- XMEAS29: component A
- XMEAS30: component B
- XMEAS31: component C
- XMEAS32: component D
- XMEAS33: component E
- XMEAS34: component F
- XMEAS35: component G
- XMEAS36: component H

Sampling frequency: **0.1 hr** with **0.1 hr dead time**.

**Product analysis, stream 11**

- XMEAS37: component D
- XMEAS38: component E
- XMEAS39: component F
- XMEAS40: component G
- XMEAS41: component H

Sampling frequency: **0.25 hr** with **0.25 hr dead time**.

## 5. Disturbances — IDV

The core source declares `IDV(1..20)`.

The documented disturbances are:

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

### Important disturbance-count discrepancy

`temain_mod.f` says that there are **21 programmed disturbances**, while the visible `IDV` common block is declared as `IDV(20)` and `teprob.f` documents IDV1 through IDV20.

We therefore record **20 explicit IDV slots in the core model** and treat the statement about 21 disturbances as an item requiring further source/data investigation rather than inventing an IDV21 interface.

## 6. Simulation time and integration

The reference examples make an important distinction between process time and output sampling.

### Original demonstration

`temain.f` uses:

```fortran
DELTAT = 1. / 3600.
```

This is a **1-second integration step expressed in hours**.

The original example calls:

```text
CONTRL
OUTPUT
INTGTR
```

and `INTGTR` performs a simple Euler update:

```text
TEFUNC -> derivative
TIME = TIME + DELTAT
YY = YY + YP * DELTAT
```

### Modified closed-loop demonstration

`temain_mod.f` also sets:

```fortran
DELTAT = 1. / 3600.
```

and uses 1-second simulation increments. It contains a substantially larger closed-loop controller implementation.

### Design decision for process-sim

The Python API should expose time in a clear, explicit unit, preferably seconds at the platform boundary:

```python
step(dt_seconds: float)
```

The TEP adapter will convert to the model's native hour-based time representation.

This keeps the rest of the industrial platform independent of the historical Fortran convention.

## 7. Open-loop vs closed-loop reference

We should preserve both reference modes conceptually.

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

It contains a simple example PI controller for stripper level and directly modifies XMV10 as an example disturbance.

### `temain_mod.f`

This is the more relevant starting point for the industrial digital-twin use case because it provides a plant-wide closed-loop control configuration.

It contains:

- 50 process states
- 1-second integration step
- multiple controller parameter blocks
- multiple setpoints
- manipulated-variable initialization
- disturbance flags
- output files for measurements and manipulated variables
- measurement noise/randomness handling

However, it should still be treated as a **reference executable/example**, not as the Python API design.

## 8. Controller architecture observed in the reference

The modified program uses multiple controller common blocks, including controller gains, integral times and previous-error state.

This tells us that the TEP adapter should eventually be able to expose controller context, but we should not make controller internals part of the minimum process-model interface.

Phase 1 boundary:

```text
Process model
    |
    +-- measurements
    +-- manipulated variables
    +-- disturbances
    +-- state/reset
```

Controller orchestration can be layered above it.

This is important because future controllers may be:

- reference Fortran controllers
- Python controllers
- OPC UA clients
- SCADA logic
- AI agents
- MPC or optimization services

## 9. Reference execution model

The first target abstraction is:

```text
                  +------------------+
                  |  TEP reference   |
                  |  Fortran model   |
                  +--------+---------+
                           |
                    TEINIT / TEFUNC
                           |
                           v
                  +------------------+
                  |  TEP adapter     |
                  +--------+---------+
                           |
                           v
                  +------------------+
                  | ProcessSimulator |
                  | Python interface |
                  +------------------+
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
          scenarios      OPC UA       future DWSIM
```

The adapter is responsible for translation and orchestration, not scientific reinterpretation.

## 10. Proposed Python boundary

The first generic interface should remain small:

```python
class ProcessSimulator:
    def reset(self) -> None:
        ...

    def step(self, dt_seconds: float) -> None:
        ...

    def get_time(self) -> float:
        ...

    def get_measurements(self) -> dict[str, float]:
        ...

    def get_manipulated_variables(self) -> dict[str, float]:
        ...

    def set_manipulated_variable(self, name: str, value: float) -> None:
        ...
```

A lower-level TEP-specific interface may additionally expose:

```python
get_state()
set_disturbance(index, enabled)
get_disturbances()
get_raw_xmeas()
get_raw_xmv()
```

Those details should remain behind the TEP backend where possible.

## 11. Mapping strategy

We should maintain two naming layers.

### Raw/reference names

```text
XMEAS1 ... XMEAS41
XMV1   ... XMV12
IDV1   ... IDV20
```

### Engineering names

For example:

```text
XMEAS9  -> reactor.temperature
XMEAS7  -> reactor.pressure
XMEAS8  -> reactor.level
XMV10   -> reactor.cooling_water_flow
```

The raw mapping must remain available for validation because the Fortran reference speaks in XMEAS/XMV/IDV terminology.

The engineering mapping belongs in a separate mapping layer so that it can later feed the Industrial Knowledge Graph.

## 12. Validation strategy

Validation is the most important Phase 1 deliverable.

We should establish a reference test matrix before adding OPC UA or GraphDB.

### Level 1 — Interface validation

Confirm that the Python adapter can:

- initialize the model
- reset the model
- advance one second
- read 41 measurements
- read 12 manipulated variables
- preserve variable ordering
- report simulation time correctly

### Level 2 — Numerical trajectory validation

Run identical initial conditions and inputs through the reference and adapter and compare selected trajectories.

At minimum:

- reactor temperature
- reactor pressure
- reactor level
- separator level
- stripper level
- compressor work
- cooling-water temperatures
- selected composition measurements

The comparison should report:

- absolute error
- relative error where meaningful
- maximum error
- RMS error
- timestamp of maximum deviation

### Level 3 — Disturbance validation

Run selected documented IDV cases and verify that the adapter reproduces the expected qualitative and quantitative response.

Start with:

- IDV1
- IDV2
- IDV4
- IDV6
- IDV13
- IDV14
- IDV15

Random disturbances should be tested separately because reproducibility requires explicit treatment of the reference random-number behavior.

### Level 4 — Dataset validation

Verify the relationship between historical files and the live model interface.

In particular, resolve why the historical 52-column observation vector contains 11 XMV values while the process model declares 12.

Do not discard XMV12 without documenting the reason.

## 13. Reproducibility requirements

The reference source contains stochastic measurement/process behavior.

The source documentation states that the random number used for measurement noise must be changed to obtain different noise sequences.

For `process-sim`, we should instead make randomness explicit:

```text
SimulationRun
  +-- random_seed
  +-- reference_model_version
  +-- initial_conditions
  +-- input_configuration
  +-- disturbance_configuration
  +-- timestep
```

A simulation run must be reproducible whenever the same deterministic configuration and seed are supplied.

## 14. What we should NOT do yet

Phase 1 should explicitly avoid:

- translating all 50 process equations into Python
- changing the scientific equations for convenience
- putting OPC UA calls inside the process equations
- putting GraphDB calls inside the simulation timestep
- introducing a hard-coded SCADA plant model
- inventing missing disturbance definitions
- assuming historical dataset columns equal the complete live process interface
- adding AI before the reference behavior is validated

## 15. Proposed Phase 1 repository structure

As implementation begins, the project can evolve toward:

```text
process-sim/
├── README.md
├── .project
├── .pydevproject
├── src/
│   └── process_sim/
│       ├── __init__.py
│       ├── core/
│       │   └── simulator.py
│       └── backends/
│           └── tep/
│               ├── __init__.py
│               ├── adapter.py
│               ├── mapping.py
│               ├── reference.py
│               └── validation.py
├── tests/
│   └── tep/
├── docs/
│   └── tep-reference/
│       └── README.md
└── scenarios/
```

The actual Fortran reference source should remain clearly separated from the Python implementation if/when it is vendored into the repository. Its copyright and license notices must be preserved.

## 16. Phase 1 milestones

### M1 — Source inventory

- [x] Identify reference repository
- [x] Identify `teprob.f`
- [x] Identify `temain.f`
- [x] Identify `temain_mod.f`
- [x] Record 50-state model boundary
- [x] Record XMEAS/XMV/IDV interfaces
- [x] Record integration convention
- [x] Record known source/documentation discrepancies

### M2 — Build a reference runner

- [ ] Establish reproducible Fortran build
- [ ] Run the original example
- [ ] Run the modified closed-loop example
- [ ] Capture reference trajectories
- [ ] Store metadata for each reference run

### M3 — Python adapter

- [ ] Define `ProcessSimulator`
- [ ] Implement TEP adapter
- [ ] Implement reset/step
- [ ] Implement XMEAS/XMV access
- [ ] Implement basic disturbance access

### M4 — Validation harness

- [ ] Compare Python adapter with reference outputs
- [ ] Add numerical tolerances
- [ ] Add regression tests
- [ ] Add selected disturbance cases
- [ ] Document unresolved differences

### M5 — Stable Phase 1 API

- [ ] Freeze initial simulator interface
- [ ] Add engineering variable mappings
- [ ] Add run metadata
- [ ] Add deterministic seed/configuration handling
- [ ] Only then begin Industrial Twin Core work

## 17. Key conclusions from the source inspection

The initial inspection changes and strengthens our implementation plan in several ways:

1. **The TEP model is already naturally adapter-friendly.** `TEINIT` and `TEFUNC` provide a clear process boundary.
2. **The process has 50 states**, so the Python layer should not pretend the 41 measurements are the process state.
3. **There are 41 measurements and 12 manipulated variables** at the model boundary.
4. **The historical ML datasets use 52 columns**, creating an 11-XMV dataset convention that must be treated separately.
5. **The core disturbance vector has 20 declared entries**, despite the modified program's statement about 21 disturbances.
6. **The reference simulation uses a one-second integration step expressed in hours.**
7. **The modified closed-loop program is substantially richer than the original demonstration**, and is the better source for understanding plant-wide controller behavior.
8. **The Python architecture should wrap the reference rather than replace it initially.**
9. **Validation must precede OPC UA, SCADA, GraphDB and AI integration.**
10. **The adapter boundary should preserve raw XMEAS/XMV/IDV semantics while providing a separate engineering naming layer.**

## 18. References

- Original ProfBraatz repository: https://github.com/camaramm/tennessee-eastman-profBraatz
- Public fork/reference copy: https://github.com/jkitchin/tennessee-eastman-profbraatz
- Downs & Vogel, *A Plant-Wide Industrial Process Control Problem*, Computers & Chemical Engineering 17 (1993), 245–255: https://doi.org/10.1016/0098-1354(93)80018-I
- Russell, Chiang & Braatz, *Data-driven Techniques for Fault Detection and Diagnosis in Chemical Processes*, Springer, 2000: https://doi.org/10.1007/978-1-4471-0409-4
- Chiang, Russell & Braatz, *Fault Detection and Diagnosis in Industrial Systems*, Springer, 2001: https://doi.org/10.1007/978-1-4471-0347-9

## Status

**Phase 1 — reference inspection complete at the documentation level.**

The next engineering task is to create a reproducible reference runner and capture baseline trajectories. Only after those trajectories are available should the Python TEP adapter be implemented and validated.
