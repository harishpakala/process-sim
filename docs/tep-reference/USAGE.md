# TEP Integration Usage

`process-sim` uses the existing ProfBraatz `tep` package rather than implementing a second TEP simulator.

## 1. Install the ProfBraatz package

In the ProfBraatz TEP repository:

```bash
pip install -e .
```

Verify the high-level API directly:

```python
from tep import TEPSimulator

sim = TEPSimulator()
sim.initialize()

normal = sim.simulate(duration_hours=2)

sim = TEPSimulator()
sim.initialize()

fault = sim.simulate(
    duration_hours=2,
    disturbances={6: (1.0, 1)},
)

print(normal.measurements.shape)
print(fault.measurements.shape)
```

The existing API returns a `SimulationResult` containing time, 50-state trajectories, 41 measurements and 12 manipulated variables.

## 2. Use the process-sim adapter

Once the ProfBraatz package is installed in the active Python environment:

```python
from process_sim.backends.tep import TEPAdapter

sim = TEPAdapter(random_seed=123)
sim.reset()

print(sim.backend)
print(sim.get_measurements().shape)          # (41,)
print(sim.get_manipulated_variables().shape) # (12,)
print(sim.get_states().shape)                # (50,)

result = sim.simulate(
    duration_hours=2,
    disturbances={6: (1.0, 1)},
)

print(result.measurements.shape)
```

## 3. Why the adapter exists

The adapter is deliberately thin. It does not:

- copy TEP process equations
- replace the ProfBraatz simulator
- reinterpret the Fortran model
- add OPC UA calls to the process model
- make GraphDB part of the simulation loop

It provides a stable `process-sim` boundary around the existing package so that the rest of the platform does not depend directly on `tep.TEPSimulator`.

## 4. Backend selection

The ProfBraatz package supports a Python backend and an optional Fortran backend. `TEPAdapter()` leaves backend selection to `TEPSimulator`.

To require the reference Fortran backend:

```python
sim = TEPAdapter(backend="fortran")
```

To explicitly use the Python backend:

```python
sim = TEPAdapter(backend="python")
```

For Phase 1 validation, the Fortran backend is the scientific reference when it is available.

## 5. Native dimensions

The live model boundary is:

```text
states       = 50
measurements = 41   # XMEAS1..XMEAS41
MVs          = 12   # XMV1..XMV12
IDVs         = 20   # IDV1..IDV20
```

Historical TEP datasets may contain 52 columns (41 XMEAS + 11 XMV). That dataset format must not be confused with the live simulator interface.

## 6. IDV6 example

IDV6 is the documented **A feed loss (stream 1) step** disturbance.

```python
sim.set_disturbance(6, 1)
print(sim.active_disturbances())
```

For batch scheduling, use the native ProfBraatz convention:

```python
result = sim.simulate(
    duration_hours=2,
    disturbances={6: (1.0, 1)},
)
```

The value `1.0` is the disturbance activation time in hours. The value `1` enables the disturbance.

## 7. Phase 1 validation

The initial tests in `tests/test_tep_adapter.py` verify:

- 50 states
- 41 measurements
- 12 manipulated variables
- 20 disturbance slots
- initialization at time zero
- one native 1-second step
- IDV6 activation
- batch simulation result dimensions

The next validation work is numerical comparison of deterministic trajectories between the selected reference backend and the adapter, followed by selected documented disturbance cases.
