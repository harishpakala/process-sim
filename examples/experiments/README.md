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

## Variable-level response analysis

The first quantitative analysis is now implemented as:

```bash
python examples/analyze_fault_response.py \
  --run-id 3972cf14-1e97-4259-a758-5d9f2ef6026c \
  --root data/runs \
  --target XMEAS9 \
  --related XMV10 XMEAS21
```

The script uses the declared fault start/end times and reports descriptive
statistics over configurable pre-fault, fault, and post-fault windows. The
default windows are 0.25 h before activation and 0.25 h after deactivation.

It reports:

- sample count
- mean
- standard deviation
- median
- fault-minus-pre mean change
- post-minus-pre mean change
- post-minus-fault mean change

An optional `--baseline-run-id` can later be supplied to compare the same
simulation-time windows against a no-fault run. This is the preferred next
step for estimating the response attributable to the injected fault rather
than relying only on within-run differences.

Example:

```bash
python examples/analyze_fault_response.py \
  --run-id <fault-run-id> \
  --baseline-run-id <baseline-run-id> \
  --root data/runs \
  --target XMEAS9 \
  --related XMV10 XMEAS21
```

The analysis is intentionally descriptive. A single run should not be used to
make causal claims or establish a general fault-response magnitude.

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
2. variable-level response detection      [IMPLEMENTED]
              ↓
3. quantitative temporal response metrics [NEXT]
              ↓
4. repeated-seed / benchmark aggregation
              ↓
5. multi-fault attribution
              ↓
6. cross-domain / semantic reasoning
```

The original experiment configuration and provenance should remain immutable as
benchmark evidence is derived from each run.