# Blind reviewer evidence package

The exporter `scripts/export_selira_blind_dossiers.py` creates
10 dossiers (D-001 to D-010), a manifest with SHA-256 hashes,
and a blank 30-row review form. A separate case-ID mapping is created
outside the reviewer directory.

## Generate (PowerShell)

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_blind_dossiers.py" -v
python scripts/export_selira_blind_dossiers.py `
  --focused selira-xmeas7-focused.json `
  --reviewer-dir selira-blind-dossiers `
  --private-map selira-private-dossier-map.json
```

**Share only `selira-blind-dossiers/` with reviewers.**
Do not share `selira-private-dossier-map.json` or any evaluator
output until decisions are frozen. Keep the mapping out of commits
and shared archives.

The shuffle uses a fixed seed (2027) by default for reproducibility.
It is **pseudonymization, not guaranteed blinding**: knowledgeable
reviewers may recognize scenarios from their content. Use different
seed values when needed, document the chosen seed, and avoid recruiting
people familiar with the original E1–E10 labels.

Reviewers must be independent of SELiRA implementation and must
document their rationale and cited evidence for each task:
SOURCE, CAC-01, CAC-02. Allowed decisions are V/F/U;
NA is only for a consumer task explicitly out of scope.

V means the *supplied synthetic scenario* meets the evidence policy,
not that any real plant evidence has been authenticated.
F requires explicit admissible contradiction. U covers absent,
inapplicable, unauthenticated, or insufficient evidence.
No engineering authorization is implied.

E10 includes the focused GraphDB discovery report verbatim and must
not be treated as a complete authenticated engineering graph.
The original GraphDB query scope should accompany reviewer instructions.

Follow `docs/selira-independent-adjudication.md` for the review
and adjudication protocol. Obtain at least two independent reviews
per dossier/task, freeze their CSV submissions, then calculate
agreement and adjudicate discrepancies before comparing against
SELiRA or SHACL.

**Known limitations:** no independently labeled records yet; all
E1–E9 are synthetic; E10 is focused discovery; reviewer familiarity
may compromise blinding; this package does not establish statistical
generalizability.
