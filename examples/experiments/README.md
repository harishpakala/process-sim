# Controlled experiments

`process-sim` experiments separate the **scenario that is executed** from the
**ground truth that the experiment asserts**. This turns scenario execution
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

## Ground-truth validation

`ExperimentValidator` currently validates the deterministic part of the ground
truth: fault lifecycle identity and exact simulation-time boundaries.

```text
Declared ground truth
        │
        ▼
ExperimentValidator
        ▲
        │
Recorded events.parquet
```

For a scheduled fault, the validator checks:

- activation event exists
- fault type and target match
- activation time matches the declared start time
- deactivation event exists when a duration is declared
- deactivation time matches start + duration

It intentionally does **not** yet claim that an affected process variable
changed by a particular amount. That quantitative layer should be established
from controlled experiments rather than assumed in the fixture.

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
Repeated seeds are the next dimension to add after the single-run path is
validated.

## Ground truth

The first fixture records:

```text
fault:       sensor_bias
 target:      XMEAS9
start:       1.0 h
duration:    0.5 h
affected:    XMEAS9
related:     XMV10, XMEAS21
```

The model deliberately does **not** claim numerical response magnitudes yet.
Those quantitative expectations should be established from controlled runs and
validated before becoming benchmark assertions.

## Research progression

The benchmark should evolve in stages:

```text
1. deterministic fault lifecycle
              ↓
2. variable-level response detection
              ↓
3. temporal response metrics
              ↓
4. multi-fault attribution
              ↓
5. cross-domain / semantic reasoning
```

The original experiment configuration and provenance should remain immutable as
benchmark evidence is derived from each run.
