# Controlled experiments

`process-sim` experiments separate the **scenario that is executed** from the
**ground truth declared by the experiment**. This turns scenario execution
into a reproducible benchmark rather than a collection of demonstration runs.

## Experiment structure

A typical experiment contains:

- experiment identifier
- scenario name
- random seed
- duration
- expected fault label
- expected affected variables
- related variables
- optional provenance metadata

The execution path is:

```text
Experiment YAML / JSON
        │
        ├── Scenario ───────────────► ScenarioRunner
        │                                   │
        └── Ground Truth                  TEPAdapter
                                            │
                                            ▼
                                  Recording Session
                                            │
                              observations + events
                                            │
                                            ▼
                                      Run Manifest
```

`ExperimentRunner` is intentionally thin. `ScenarioRunner` remains the single
owner of simulation orchestration, fault synchronization, recording cadence,
storage, and simulator provenance. The experiment layer adds the scientific
context and persists the declared ground truth alongside the run metadata.

## Running an experiment

The first fixture is `reactor_cooling_bias_001.yaml`. Its scenario is
`examples/scenarios/reactor_sensor_bias.yaml`.

```bash
python examples/run_experiment.py \
  examples/experiments/reactor_cooling_bias_001.yaml \
  examples/scenarios/reactor_sensor_bias.yaml \
  --output data/runs
```

The experiment seed is passed to `TEPAdapter`, and the resulting run manifest
contains the experiment specification and ground-truth declaration.

## Verified first experiment

The first controlled experiment has been executed and inspected successfully.
Run:

```text
3972cf14-1e97-4259-a758-5d9f2ef6026c
```

Configuration:

```text
experiment:       reactor_cooling_bias_001
scenario:         reactor_sensor_bias
seed:             42
duration:         2.0 h
record interval:  1 native step
variables:        53
observation rows: 381,653
event rows:       4
```

The persisted event sequence is:

```text
0.0 h   SimulationStarted
1.0 h   FaultActivated     XMEAS9
1.5 h   FaultDeactivated   XMEAS9
2.0 h   SimulationCompleted
```

This verifies the deterministic execution and temporal ground-truth layer for
the fixture. Recording every native step produces 7,201 snapshots, and
`7,201 × 53 = 381,653` observations.

The experiment is accelerated simulation: 2.0 simulated hours do not imply 2.0
wall-clock hours.

## Ground truth status

The current experiment establishes deterministic ground truth for:

- fault lifecycle identity
- fault target
- activation time
- deactivation time
- simulation completion
- persisted experiment provenance

It intentionally does **not** yet assert a numerical process response. In
particular, the declared `affected` and `related` variables are hypotheses to
be evaluated against the recorded observations rather than treated as already
proven causal effects.

For the current fixture:

```text
fault:       sensor_bias
target:      XMEAS9
start:       1.0 h
duration:    0.5 h
affected:    XMEAS9
related:     XMV10, XMEAS21
```

## Next experimental layer: variable response analysis

The immediate next step is to quantify the response around the known fault
window:

```text
                 fault window
                     │
                     ▼
XMEAS9   ────────────████████████────────────
                     1.0       1.5 h

XMV10    ────────────────────────────────────
                     ?

XMEAS21  ────────────────────────────────────
                     ?
```

The analysis should compare pre-fault, fault, and post-fault windows and report
at least:

- baseline mean and standard deviation
- fault-window mean and standard deviation
- measured change / bias magnitude
- onset and recovery timing
- response latency where applicable
- settling or recovery behavior
- related-variable response for `XMV10` and `XMEAS21`

The first implementation should be descriptive and deterministic. Statistical
or causal claims should only be added after repeated controlled runs support
them.

## Initial benchmark matrix

`benchmark_matrix.yaml` defines the first benchmark families:

1. normal baseline
2. sensor bias
3. sensor drift
4. actuator stuck
5. process disturbance
6. combined faults

The corresponding scenario fixtures live under `examples/scenarios/`. The
matrix is a benchmark specification, not yet an automated batch executor.
Repeated seeds are the next dimension after the single-run analysis path is
validated.

## Research progression

The benchmark should evolve in stages:

```text
1. deterministic fault lifecycle          [ACHIEVED]
              ↓
2. variable-level response detection      [NEXT]
              ↓
3. temporal response metrics
              ↓
4. repeated-seed / benchmark aggregation
              ↓
5. multi-fault attribution
              ↓
6. cross-domain / semantic reasoning
```

The original experiment configuration and provenance should remain immutable as
benchmark evidence is derived from each run.