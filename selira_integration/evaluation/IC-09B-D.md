# IC-09B–D bounded verification

Additive tests only. IC-09A and historical results remain unchanged.

- B: 20 configurations per migrated contract (40 total), explicit expected focus and violation sets, independent AST and SHACL.
- C: 24 combinations of three caller attestations and three candidate states, plus mixed F/U precedence. Atomic graph/version checks.
- D: 16 snapshots per migrated contract, 256 ordered pairs each (512 total), exact affected set, unchanged control node, and three conservative fallback checks per contract. Logical counts only. Expected per contract: 496 full, 228 selective evaluations. These are design expectations until execution.

Run from repository root (PowerShell):

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/selira/test_ic09_bounded_runtime.py -q
Push-Location selira_artifact
python -m pytest tests/test_ic09_bounded_identifier.py -q
Pop-Location
```

Use the existing artifact environment for the second command. Predicate targeting excludes nodes with no authoritative identifier. The finite spaces are not proofs over arbitrary graphs. Attestations are caller-supplied, not authenticated. No runtime speedup is claimed.
