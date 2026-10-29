# TEP-C02 — Measurements contract

**Status:** Proposed compact architectural contract; implementation coverage varies. This tuple is a semantic model, not a claim that the adapter directly returns all fields.

## Formal representation

\[
C_meas(i,k) = (I_i, V_(i,k), U_i, T_k, R_run, P)
\]

**Elements:** I_i: XMEAS signal identity; V_(i,k): measured value at step k; U_i: engineering unit; T_k: simulation time; R_run: recording run ID; P: observation provenance.

**Constraint:** i ∈ {1,…,41}. Measurement identity alone does not establish engineering asset identity.

**Implementation boundary:** TEPAdapter supplies signal-array values and native time; units are mapped by platform metadata, while run ID/provenance are added by recording infrastructure.

**Verification:** Confirm the proposed representation against adapter, simulator, scenario and recording tests before treating it as a fully verified guarantee.
