# AssetInventory–ProductCatalog reference consistency (2026-10-23)

## Completed

Updated 33 active `ProductReference` values: 3 pressure, 5 temperature, 3 level, 10 flow, 11 valve, 1 compressor power measurement. All 33 now resolve to active ProductCatalog `AssetIdentifier` values. Changed references have `PreviousProductReference` for provenance. Proposed family status remains distinct from engineering approval.

## Full inventory check

- AssetInventory assets: **62**
- ProductCatalog entries: **17**
- Active ProductReference fields failing exact URI match: **5** (listed below)
- Other **57** active ProductReference values resolve against ProductCatalog.

| Asset | Unresolved reference | Decision / follow-up |
|---|---|---|
| TEP_XMV12 | `Rittal_3244100` | Agitator command, not valve; verify appropriate motor/drive or agitator reference |
| TEP_M_1301 | `Rittal_3244100` | Illustrative motor; optional pump extension separate, no motor selection |
| TEP_M_1401 | `Rittal_3244100` | Compressor drive concept; verify motor family |
| TEP_M_1501 | `Rittal_3244100` | Illustrative motor; optional pump extension separate |
| TEP_CV_1401 | `Siemens_S55264_V193` | Separate illustrative valve; verify actual duty before mapping |

**Important:** The SAMSON_3241_7 catalog record describes a specific DN25/Kvs10/PN40 valve assembly. All eleven XMV mappings are **family-level proxies only**, not approvals of this specific assembly. Future improvement: add a distinct family-only catalog entry and point XMV1–XMV11 to it.

**Important:** XMEAS20 electrical energy meter is only a conditional proxy for thermodynamic compressor work; no equivalence asserted.

This is a structural reference-consistency audit, **not** AAS schema validation, SHACL validation, ECLASS verification or CI test execution.
