# Family assignments for previously unresolved hardware (2026-10-23)

| Asset | Assigned reference family | Engineering interpretation |
|---|---|---|
| TEP_XMV12 | EKATO HWL-N engineered agitator package | Logical stirring control; drive rating and control mapping unverified |
| TEP_M_1301 | ABB Process performance induction motor | Optional liquid-pump extension only; motor power/torque not sized |
| TEP_M_1401 | ABB Process performance induction motor | Gas compressor drive concept; compressor work ≠ motor nameplate power |
| TEP_M_1501 | ABB Process performance induction motor | Optional liquid-pump extension only; motor power/torque not sized |
| TEP_CV_1401 | SAMSON Type 3241 family | Compressor control valve candidate; valve sizing, trim and actuator unverified |

**Catalog distinction:** New `SAMSON_3241_Family_Candidate` does not represent the existing `SAMSON_3241_7` DN25/Kvs10/PN40 assembly. The latter still needs separate remediation for XMV1–XMV11.

**Reference consistency:** 38 populated AssetInventory ProductReferences, 0 unresolved exact URI matches against 22 catalog entries. The other 24 assets have no ProductReference. This is not validation of real equipment, configured products, AAS schema, SHACL, or ECLASS classifications.

**Required for orderable equipment:** Pump head, NPSH and efficiency; motor load/speed/torque/voltage; agitator mechanical duty; valve Kv and fail action. Original missing references are retained as PreviousProductReference.
