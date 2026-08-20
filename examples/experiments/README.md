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

## Paired multi-seed replication

For the controlled fault benchmark, the preferred next step after validating a
single run is to repeat the **same fault experiment and a matching no-fault
baseline at several seeds**. The replication runner automates that pairing and
keeps the experimental protocol fixed while changing only the random seed.

```bash
python examples/run_replication.py \
  examples/experiments/reactor_cooling_bias_001.yaml \
  examples/scenarios/reactor_sensor_bias.yaml \
  examples/scenarios/reactor_no_fault.yaml \
  --seeds 42 43 44 45 46 \
  --output data/runs \
  --summary data/replications/reactor_cooling_bias.csv
```

For every seed, the runner:

1. creates a seed-specific fault experiment in memory;
2. creates a paired no-fault baseline with the same seed and duration;
3. runs both through `ExperimentRunner` and `TEPAdapter`;
4. aligns observations on `simulation_time_hours`;
5. calculates mean delta, MAE, RMSE, maximum absolute delta, and time of the
   maximum deviation for the fault and post-fault windows; and
6. writes a CSV summary plus a JSON manifest containing the paired run IDs.

No seed-specific YAML files are required. The original experiment fixture
remains the source of truth for fault definition, duration, and expected ground
truth.

The summary contains one row per seed and measured variable, including the
fault run ID and baseline run ID. This makes the output directly usable for a
later statistical aggregation step.

## Fault-magnitude response sweep

After repeated-seed replication, the next controlled experiment varies the
**fault magnitude** while preserving the same fault timing, duration, simulator,
paired-baseline protocol, and measured variables. The first planned sweep is
`+1`, `+5`, and `+10` sensor-bias units over seeds `42`, `43`, and `44`.

The sweep runner is:

```bash
python examples/run_fault_magnitude_sweep.py \
  examples/experiments/reactor_cooling_bias_001.yaml \
  examples/scenarios/reactor_sensor_bias.yaml \
  examples/scenarios/reactor_no_fault.yaml \
  --magnitudes 1 5 10 \
  --seeds 42 43 44 \
  --output data/runs \
  --summary data/replications/reactor_cooling_bias_magnitude_sweep.csv
```

For each magnitude/seed pair it runs one fault experiment and one matching
no-fault baseline. The detailed output contains:

- mean delta
- MAE
- RMSE
- maximum absolute delta
- time of maximum absolute delta
- integrated absolute error (IAE)
- integrated squared error (ISE)
- paired run IDs and seed/magnitude provenance

The aggregate output reports mean, standard deviation, minimum, maximum, and
coefficient of variation across seeds for each magnitude and measured variable.
The JSON manifest records the complete sweep design and all generated run IDs.

This experiment is intended to answer whether the observed closed-loop response
is not only reproducible, but also systematically distinguishable as the fault
magnitude changes. It is a response-characterization experiment, not by itself
a causal proof.

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

The first quantitative analysis is implemented as:

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

An optional `--baseline-run-id` compares the same simulation-time windows
against a no-fault run. This is the preferred single-pair analysis because it
separates ordinary trajectory variation from the fault-versus-baseline
trajectory difference.

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

The corresponding scenario fixtures live under `examples/scenarios/`.
Repeated-seed execution is now automated for the first controlled benchmark;
the magnitude sweep extends that benchmark into a response-characterization
matrix.

## Research progression

The benchmark should evolve in stages:

```text
1. deterministic fault lifecycle          [ACHIEVED]
              ↓
2. variable-level response detection      [IMPLEMENTED]
              ↓
3. paired fault-vs-baseline analysis      [IMPLEMENTED]
              ↓
4. repeated-seed replication              [IMPLEMENTED]
              ↓
5. fault-magnitude response sweep         [IMPLEMENTED]
              ↓
6. multi-fault attribution
              ↓
7. cross-domain / semantic reasoning
```

The magnitude sweep is the final planned experiment family for closing the
initial controlled-response benchmark. Its execution and scientific results
must be completed and inspected before claiming this phase as empirically
validated.

The original experiment configuration and provenance should remain immutable as
benchmark evidence is derived from each run.
