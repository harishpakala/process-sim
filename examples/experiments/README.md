# Controlled experiments

Experiment specifications separate the **scenario that is executed** from the
**ground truth that the experiment asserts**.

A typical experiment contains:

- experiment identifier
- scenario name
- random seed
- duration
- expected fault label
- expected affected variables
- related variables
- optional provenance metadata

The first fixture, `reactor_cooling_bias_001.yaml`, is deliberately small. It
is intended to become the first member of a controlled benchmark suite rather
than a one-off demonstration.

## Planned benchmark families

1. normal baseline
2. sensor bias
3. sensor drift
4. actuator fault
5. process disturbance
6. combined faults
7. repeated seeds

The experiment specification does not yet claim that an affected variable will
actually change by a particular amount. Those quantitative expectations should
be added only after they are established from the simulator and validated by
experiments.
