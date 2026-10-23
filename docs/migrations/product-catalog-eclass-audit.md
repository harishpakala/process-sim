# ECLASS classification audit (2026-10-23)

The ProductCatalog template requires `ECLASSClass`, `ECLASSPreferredName`, and `ECLASSIRDI` for each entry. The template was **not changed**.

After the partial remediation, **13/22** catalog entries contain all three fields, while **9/22** remain incomplete. The eleven pre-existing complete entries have not been independently authenticated against an official ECLASS release. Two additional family records reuse same-category classification triples from existing catalog entries and remain pending official verification.

## Entries still missing ECLASS classifications

- `EandH_FMR62B_Candidate`
- `EandH_TMass_F300_Candidate`
- `EandH_Promass_F300_Candidate`
- `EandH_Prowirl_F200_Candidate`
- `EandH_PMP51B_Candidate`
- `KSB_Multitec_HighPressure_Candidate`
- `Unspecified_MotorDrive_Reference`
- `Unspecified_AgitatorDrive_Reference`
- `ABB_ProcessPerformance_InductionMotor_Candidate`

**Do not invent ECLASS IRDIs or reuse an unrelated class** merely to satisfy SHACL. In particular, the existing synchronous-motor classification is not evidence for an induction motor. The two `Unspecified_*` records are placeholders, not actual manufacturer products; they should be replaced by genuine classified products or removed from ProductCatalog after updating their references.

Use the official ECLASS class lookup to confirm the 8-digit class code, official preferred name, IRDI, release and language: https://eclass.eu/en/eclass-standard/search-content . SHACL is expected to continue failing while required fields are missing. No SHACL or GraphDB validation was executed here.
