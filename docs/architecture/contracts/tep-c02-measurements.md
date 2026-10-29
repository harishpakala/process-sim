# TEP-C02 — Measurements contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_meas(i,k) = (I_i, V_(i,k), U_i, T_k, R_run, P)
\]

## Tuple elements

| Symbol | Meaning | Source |
| --- | --- | --- |
| `I_i` | XMEAS signal identifier, i = 1,…,41 | TEP signal indexing |
| `V_(i,k)` | Measurement value for signal i at step k | TEPAdapter.get_measurements() |
| `U_i` | Engineering unit for signal i | Platform signal metadata |
| `T_k` | Simulation timestamp (hours) | TEPAdapter.get_time_hours() |
| `R_run` | Recording run identifier | Recording layer |
| `P` | Observation provenance | Recording/event layer |

**Constraint:** i ∈ {1,…,41}. Measurement identity alone does not establish engineering asset identity.

**Implementation boundary:** TEPAdapter supplies signal-array values and native time; units are mapped by platform metadata, while run ID/provenance are added by recording infrastructure.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
