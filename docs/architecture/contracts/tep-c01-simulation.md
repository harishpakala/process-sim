# TEP-C01 — Simulation Lifecycle and Time Contract

**Version:** 0.1 (implementation-grounded draft, 29 October 2026)  
**Contract boundary:** `process_sim.backends.tep.TEPAdapter`; operational lifecycle exposed separately by `process_sim.protocols.opcua.OPCUAServer`.  
**Normative source:** current branch implementation. The requirements below distinguish **enforced adapter behavior**, **observed tests**, and **proposed stricter guarantees**. This is not a proof of the ProfBraatz native implementation.

## 1. Concrete interface

```python
TEPAdapter(
    backend: str | None = None,
    random_seed: int | None = None,
    control_mode: str = "closed_loop",
    fault_manager: FaultManager | None = None,
    fault_event_sink: Callable[[dict], None] | None = None,
)
reset() -> None
step(n_steps: int = 1) -> bool
get_time_hours() -> float
get_measurements() -> numpy.ndarray    # observed shape (41,)
get_manipulated_variables() -> numpy.ndarray  # observed shape (12,)
get_states()                           # observed shape (50,)
get_disturbances()                     # observed shape (20,)
set_manipulated_variable(index: int, value: float) -> None
set_disturbance(index: int, value: int = 1) -> None
clear_disturbances() -> None
sync_faults() -> None
```

`backend` is forwarded to the external `tep.TEPSimulator` only when supplied. `random_seed` and the enum-converted `control_mode` are passed to the native constructor. Supported mode strings depend on `tep.ControlMode`; this repository explicitly uses `closed_loop` (default) and `manual` (OPC UA launcher). Other native modes must not be assumed.

The generic `ProcessSimulator` protocol lives at `src/process_sim/core/simulator.py`: `reset`, `step`, `get_time_hours`, `get_measurements`, `get_manipulated_variables`, and `set_manipulated_variable`.

## 2. State model — observable, not an invented native state machine

The adapter has **no explicit lifecycle-state enum**. Its `step` implementation reads `simulator.initialized` and initializes the native simulator on demand. Accordingly, define the following *abstract* states for contract analysis only:

- `U` — native simulator reports `initialized == False`.
- `I` — native simulator reports `initialized == True`.
- `E` — a `step` call raises an exception; not a stored or automatically recoverable state.

Allowed adapter-level transitions:

| Operation | Preconditions | Actual implementation action | Observable postcondition |
| --- | --- | --- | --- |
| `reset()` | Adapter constructed; native `initialize()` succeeds | Calls `simulator.initialize()`, clears adapter fault bookkeeping, optionally installs controller wrapper | Native simulator reinitialized; time expected to reset to zero (tested) |
| `step(1)` from `U` | Native initialization and step succeed | Calls native `initialize()`, synchronizes faults, invokes native `step(n_steps=1)`, synchronizes faults again | Native state initialized; returned value is native step result |
| `step(n)` from `I` | `n >= 1`; each native call succeeds | Repeats one-step native calls `n` times, with fault synchronization around each | Time and process state reflect `n` native steps; returns **last** native result |
| `get_time_hours()` | Native time attribute readable | `float(simulator.time)` | Returns native reported simulation time in hours |
| `step(n)` where `n < 1` | None | Raises `ValueError("n_steps must be >= 1")` before stepping | No native step invoked by this method |
| `reset()` after a prior run | Native initialization succeeds | Reinitializes native simulator and resets adapter bookkeeping | Fresh native initial conditions; **not** a new run identifier |

**Important:** There is no adapter-level `start()` or `stop()` method. Running/stopped controls belong to the OPC UA server, not `TEPAdapter`. The native implementation may have additional states or exceptions not covered by this abstraction.

## 3. Design-by-contract clauses

Let `t(S) = float(S.simulator.time)`, and let `step_1` denote one successful native step. Let `Δ = 1/3600 h` denote the one-second native step **observed in the repository's adapter test**, not an unconditional guarantee for every version/backend of the external `tep` package.

### C01-PRE-01 — Valid step count (enforced)

```text
requires: n_steps >= 1
otherwise: ValueError("n_steps must be >= 1")
```

The code does not explicitly enforce Python integer type, finite numeric values or an upper limit. Values such as floats can fail later at `range(n_steps)` rather than through the named precondition. A stronger type contract remains **proposed**.

### C01-POST-01 — Native step dispatch (enforced by adapter loop)

```text
Given: step(n) completes normally and n is a positive integer
Ensures: exactly n invocations of native simulator.step(n_steps=1)
         and 2n calls to adapter.sync_faults()
Returns: the result of the nth native step (no aggregation)
```

If a native step throws, prior steps are **not rolled back**. There is no adapter transaction or automatic recovery. If the native step returns `False`, the loop does not stop early; it proceeds unless an exception is raised.

### C01-TIME-01 — Time progression (observed, not universally proven)

```text
On tested backend/fixture:
    t(reset()) = 0 hours
    t(step(1) after reset()) ≈ 1 / 3600 hours

Candidate invariant for future conformance tests:
    successful native step => t_next >= t_previous
```

Do not claim strict monotonicity, exact step duration for all backends, or that returning `True` establishes a physical stability guarantee. Those require testing the external native simulator. `get_time_hours()` does not synthesize a timestamp or track elapsed wall time.

### C01-RESET-01 — Reset scope (enforced and bounded)

A successful `reset()` calls `simulator.initialize()` and clears `_active_fault_ids`, `_fault_managed_idvs`, and `_fault_previous_idvs`; the native controller is wrapped again when external control is disabled. The attached `FaultManager` is **not cleared**. Consequently previously registered fault definitions may reactivate after resetting time. The reset does not create, clear or close a recording session.

### C01-MODE-01 — Control ownership (enforced selection)

```text
external_control == (control_mode == "manual")
if external_control:
    adapter does not install the fault-aware native controller
else:
    adapter attempts to wrap the native controller after initialization
```

The OPC UA launcher constructs `TEPAdapter(random_seed=seed, control_mode="manual")`. For manually controlled experiments, the caller must issue XMV writes; starting the simulation alone does not guarantee a closed-loop controller.

### C01-FAULT-01 — Step-boundary event synchronization (enforced)

For each step, the adapter runs `sync_faults(); native.step(1); sync_faults()`. Fault scheduling is evaluated against native simulation time at these boundaries. This does **not** promise sub-step activation accuracy or atomic synchronization with a separate recorder. Lifecycle semantics are specified in TEP-C05.

### C01-DET-01 — Reproducibility boundary (partial)

The seed is stored on the adapter and forwarded to the native constructor. **Repeatability for equal seed, backend, initial state, control input and disturbance sequence is a testable hypothesis, not a guarantee established by this adapter code.** Backend versions, controller mode, external control timing and native implementation can affect trajectories.

## 4. OPC UA operational lifecycle — distinct interface

The OPC UA server publishes `TEP/Simulation/TimeHours`, `Running`, `ControlMode`, `RealTimeFactor`, and methods `Start()`, `Stop()`, `Reset()` returning OPC UA Boolean variants. It maintains `_simulation_task` for operational running state.

| Invocation | Observable behavior in `OPCUAServer` |
| --- | --- |
| `Start` | Creates an asynchronous simulation loop unless an active loop already exists; returns `True` |
| `Stop` | Cancels/awaits the loop (if any), publishes `Running=False`, returns `True` |
| `Reset` | Stops loop, calls adapter `reset()`, reconfigures fault hooks, publishes `Running=False`, returns `True` |
| Simulation tick | Sleeps `update_interval_seconds`; computes `max(1, int(round(update_interval_seconds * real_time_factor)))` steps; applies OPC UA XMV changes before **each** step |
| Validation | Constructor rejects `real_time_factor <= 0` and `update_interval_seconds <= 0` with `ValueError` |

The scheduling formula is a **code-level rule**, not a wall-clock real-time guarantee. No explicit locking or transactional guarantee between OPC UA commands and asynchronous ticks is established here. `Running` is a published status variable and may update only when `update()` runs.

## 5. Failure and non-guarantees

| Case | Current handling | Contract implication |
| --- | --- | --- |
| Missing external `tep` package | Adapter constructor raises explanatory `ImportError` | Initialization cannot proceed |
| Invalid native control mode | Adapter constructor raises `ValueError` with valid native enum modes | Reject invalid configuration |
| `step(0)` or `step(-1)` | `ValueError` | Native step not invoked |
| Native initialization/step exception | Propagates; no rollback provided | Partial progress possible |
| Native step returns `False` | Value passed back after loop completes | Caller must interpret native result |
| Reset with registered scheduled faults | Adapter bookkeeping resets; manager remains populated | Prior definitions are **not** automatically deleted |
| Two simultaneous callers invoking `step` | No adapter lock present | Thread-safety **not established** |
| `simulate(...)` batch API | Delegates directly to native `simulate` | Does **not** inherit adapter `step` fault-sync guarantee without verification |

## 6. Concrete verification matrix

| Property | Test / implementation anchor | Evidence status |
| --- | --- | --- |
| Native dimensions and reset time | `tests/test_tep_adapter.py::test_tep_adapter_initializes_with_expected_dimensions` | Test exists; external `tep` dependency; not executed in this review |
| Native one-step time `≈ 1/3600 h` and return `True` | `tests/test_tep_adapter.py::test_tep_adapter_advances_one_native_step` | Test exists; not executed in this review |
| Manual control mode and XMV write | `tests/test_tep_adapter.py::test_external_control_mode_uses_manual_tep_control` | Test exists; not executed in this review |
| Reject invalid control mode | `tests/test_tep_adapter.py::test_invalid_control_mode_is_rejected` | Test exists; not executed in this review |
| Fault activation/deactivation on one-second boundaries | `tests/test_tep_adapter.py::test_fault_lifecycle_events_are_emitted_at_simulation_boundaries` | Test exists; not executed in this review |
| `step(n)` dispatches exactly `n` native steps | Adapter loop inspection | Implemented; targeted test not identified |
| Reset preserves registered fault definitions | Adapter code inspection | Implemented behavior; targeted test not identified |
| Multi-step monotonicity across both supported backends | No cited complete conformance suite | **Specified for future verification** |
| Seed reproducibility including manual-control sequence | No cited complete conformance suite | **Specified for future verification** |
| Concurrent operation safety and precise wall-clock scheduling | No guarantee established | **Unspecified / unverified** |

Run relevant existing tests from the repository root after installing the external TEP dependency:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m pytest tests/test_tep_adapter.py -v
```

Because `pytest.importorskip("tep")` is used, a skipped suite **does not** constitute a passing conformance check.

## 7. Traceability and next actions

- **TEP adapter:** `src/process_sim/backends/tep/adapter.py`.
- **Generic simulator protocol:** `src/process_sim/core/simulator.py`.
- **Operational lifecycle:** `src/process_sim/protocols/opcua/server.py`.
- **Operational launcher:** `examples/run_opcua_server.py`.
- **Tests:** `tests/test_tep_adapter.py`.
- **External dependency:** ProfBraatz `tep.TEPSimulator` (native internals not audited in this document).

Before declaring TEP-C01 conformant, add tests for invalid step types, multi-step time progression, reset with retained faults, native-step failures, backend-specific reproducibility and OPC UA lifecycle state transitions. Formal verification is **not** claimed.
