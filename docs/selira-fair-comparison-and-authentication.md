# Fair comparator and authenticated-evidence roadmap

## Comparator status

`scripts/selira_shacl_decision_policy.py` defines an independently
coded **findings-to-decision** mapping with explicit verified,
contradiction, and missing evidence states. It distinguishes source
qualification, consumer fitness, and integrated consumer decisions.

**This is NOT yet a SHACL-SPARQL implementation or fair head-to-head
comparison.** It is a policy oracle to be connected to actual SHACL
validation findings. In particular, the script currently receives
preclassified findings, so it cannot demonstrate detection capability.
Do not report comparative accuracy from it.

To complete the comparison:
1. Define RDF input schema for each SC and CAC requirement.
2. Create SHACL-SPARQL constraints that output explicit evidence
   finding classes (verified, contradiction, insufficient).
3. Build a common input encoder with no SELiRA verdict leakage.
4. Derive SHACL decisions from its own validation report and compare
   case-by-case against SELiRA with matching input scope.
5. Test E1–E10 first, then new frozen cases, and publish disagreements.

## Authentic evidence status

`scripts/audit_selira_evidence.py` checks local artifact existence,
path safety, and SHA-256 agreement with a supplied manifest. It
**does not authenticate issuer identity or provenance**. Hashes and
issuer strings are self-asserted until verified against independent
trusted signatures or authenticated acquisition channels.

To claim one end-to-end XMEAS7 case, obtain:
- Source exports with verifiable issuers for DEXPI, ECAD and PLC
  identifiers, including revision/configuration and provenance.
- OPC UA namespace/node mapping plus independently authenticated
  server identity, session, and binding observations.
- Time-bounded TEP XMEAS7 measurements with traceable acquisition,
  units, timestamps, and integrity records.
- Documented source-to-signal reconciliation, consumer task requirements,
  and approval/authorization evidence where applicable.
- Trust anchor, signature validation, and independent verification
  records for each relevant evidence item.

Missing items remain U. The audit always returns
`authenticatedEndToEndChain=false` and `authorization=false`
until a real verifier is implemented and independently validated.

## Reproduction

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_fair_comparison_and_evidence.py" -v
python scripts/audit_selira_evidence.py `
  --manifest evidence-manifest.json `
  --evidence-root . `
  --output selira-evidence-audit.json
```

The audit command requires a user-supplied evidence manifest; none is
fabricated. Do not publish private plant credentials, certificates with
secrets, or sensitive industrial operational records.
