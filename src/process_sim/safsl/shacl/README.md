# SAFSL → SHACL compiler (SC-01 subset)

This backend is implemented within process-sim; it does not change the upstream
SAFSL_Compiler_Tool_Chain or its IEC 61499 backend.

## CLI

From the repository root, with `PYTHONPATH=src` and the dependencies
`lark`, `rdflib`, `pyshacl` installed:

```bash
python -m process_sim.safsl.shacl.compiler \
  examples/safsl/asset_product_integrity.safsl \
  examples/safsl/bindings.example.json \
  /tmp/selira-shacl
python -m unittest discover -s tests -p 'test_safsl_shacl_sc01.py'
```

The CLI emits `integrity_shapes.ttl` and `contract_manifest.json`.

## Contract and evidence semantics

The compiler currently accepts a contract-only SAFSL grammar supporting
`forall` + `existsExactlyOne` + `matches` only. It is deliberately
separate from the copied legacy Process grammar; merging them remains work.

The JSON bindings are explicit stand-ins for verified ONTO NEXUS mappings.
The sample template IDs and RDF IRIs are illustrative, NOT production IDs.
Template references use canonical UTF-8 Base64 encoding, matching existing
SAFSL examples.

The SHACL shape assumes the validation graph is a complete, authoritative
snapshot. SHACL reports zero and multiple matches as violations in that
snapshot. Incomplete evidence must be classified U by the Automation Manager,
not automatically F. Empty focus populations must be classified NA, not V.
Changes to either template invalidate SC-01 and require revalidation of all
affected assets. Canonical entity identity must be normalized before
validation; two RDF nodes for one entity are not automatically merged.

## Known limitations

- No runtime Automation Manager admission/compare-and-commit integration.
- No production template resolver or real AAS template IDs.
- No general-purpose quantified SAFSL compiler; only the SC-01 operator subset.
- No runtime V/F/U/NA evidence decision engine.
- No tests executed by the repository changes themselves.
- No guarantee of package-data inclusion in wheel builds without packaging review.
