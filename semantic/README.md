## Run all three domains without arguments

From the repository root:

```bash
python3.12 -m semantic.template_lifting
python3.12 -m semantic.instance_lifting
```

The default targets are defined in `semantic/config.py` and include DEXPI, ECAD and ProductCatalog. Turtle outputs are written to `out/semantic/{domain}-template.ttl` and `out/semantic/{domain}-instance.ttl`. Defaults do **not** push to GraphDB or run SHACL validation; use `--push` or `--validate` explicitly. Existing single-target CLI arguments remain supported.

Note: scripts use absolute paths derived from their package location, so inputs resolve regardless of the working directory, but execute as modules from the repository root to make the package importable.

# Generic AAS semantic lifting (SAFSL integration)

Adapted from [SAFSL Compiler Tool Chain](https://github.com/harishpakala/SAFSL_Compiler_Tool_Chain), Apache-2.0. The original lifting implementation is preserved in structure and extended with a domain namespace and command-line entry points.

## Dependencies

Python 3.12, `rdflib`, `pyshacl`, `aas-core3.1` (module `aas_core3_1`), and `requests`. See upstream `requirements.txt` for compatible pinned versions. Run commands from the **repository root** so `semantic` imports resolve.

## Generic template lifting

```bash
python3.12 -m semantic.template_lifting --domain dexpi --input semantic/templates/dexpi_template.json --output out/dexpi-template.ttl
python3.12 -m semantic.template_lifting --domain ecad --input semantic/templates/ecad_template.json --output out/ecad-template.ttl
python3.12 -m semantic.template_lifting --domain productcatalog --input semantic/templates/product_catalog_template.json --output out/product-catalog-template.ttl
```

Add `--push` to upload a named graph to GraphDB (default configured in `semantic/ontoutils.py`: `http://localhost:7200/repositories/AAS/statements`). Local generation does not require GraphDB.

## Generic instance lifting

```bash
python3.12 -m semantic.instance_lifting --domain productcatalog --template semantic/templates/product_catalog_template.json --input examples/aas/product_catalog_instance.json --validate --output out/product-catalog-instance.ttl
python3.12 -m semantic.instance_lifting --domain ecad --template semantic/templates/ecad_template.json --input examples/aas/tep_ecad_instance.json --validate --output out/ecad-instance.ttl
python3.12 -m semantic.instance_lifting --domain dexpi --template semantic/templates/dexpi_template.json --input examples/aas/tep_dexpi_instance.json --validate --output out/dexpi-instance.ttl
```

`--validate` performs local pySHACL validation using the supplied template. `--push` publishes the RDF graph to GraphDB. Do not add `--push` until the graph and validation output have been reviewed.

## ProductCatalog repeating products

The ProductCatalog template declares a `Products.Product` collection with `ZeroToMany` cardinality, whereas the instance names individual product collections `Products.SMC_PSE550`, etc. Instance lifting automatically infers the template's repeated-child predicate (`hasProduct`) for the children of `Products`. The RDF resources retain distinct deterministic URIs and original `idShort` labels.

The ProductCatalog namespace is `https://example.org/productcatalog/`. Other domains can be added to `semanticDict` in `semantic/ontoutils.py`; the lifting scripts do not require per-domain branches.

## Current limits

- The template's `TechnicalProperties` collection does not constrain the many manufacturer-specific property names. These are lifted as string literals with predicates based on their `idShort`, including `SpecificationSourceURL`. QUDT typed quantities and explicit unit resources are not yet implemented.
- Only AAS Property, Range, SubmodelElementCollection, and RelationshipElement are lifted by upstream logic; other element types are skipped with a warning.
- The GraphDB endpoint remains a local default and must be configured for the deployment environment.
- Copying and adapting the scripts is not evidence that end-to-end RDF/SHACL/GraphDB tests have passed. Run the commands above in an environment with dependencies and GraphDB installed.
