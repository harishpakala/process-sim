# Experimental SHACL subgraph planner (DEXPI first)

This branch introduces an **isolated deterministic extraction layer** at
`src/process_sim/dtwise/experimental_shacl_subgraph.py`. It reuses the
existing `semantic/ontology2/dtwise/dtwise-schema-index.json` without
rebuilding or flattening the ontology.

## Responsibilities

- At initialization: index SHACL NodeShapes, property ownership, and directed
  `sh:node` relationships (resolved through property shapes and `sh:path`).
- Per query: exact-name grounding of shapes and properties, including
  property-to-owner lookup.
- Extract a compact candidate graph. Independent anchors stay disconnected
  unless the caller explicitly requests structural connection.
- Preserve source predicate IRIs, property-shape IRIs, and evidence IDs.
- Never invent missing relationships.

## Usage

```python
from process_sim.dtwise.experimental_shacl_subgraph import load_index, extract_question

index = load_index("semantic/ontology2/dtwise/dtwise-schema-index.json")
graph = extract_question(
    index,
    "Show MeasuredVariable of InstrumentationFunction and "
    "ActuatedVariable of ActuatingFunction",
)
assert len(graph["nodes"]) == 2
assert graph["edges"] == []
```

## Scope and limitations

This is **phase 1**, not an end-to-end LLM planner. It does not yet call an
LLM, generate SPARQL, recognize synonyms, or interpret whether two independently
named shapes must share a root. `connect=True` is an explicit structural
operation, not an automatic interpretation of natural language.

The connection algorithm currently finds **one shortest directed path**
between each anchor and the first anchor. It does not preserve all alternative
routes, discover a minimum Steiner subgraph, or handle reverse traversal and
branching semantic choices. Those are next-phase tasks; no completeness
guarantee is implied.

Tests: `pytest tests/test_experimental_shacl_subgraph.py`.
