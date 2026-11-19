# Query Intent Catalog — SHACL-grounded SPARQL planner

**Status:** design inventory, not an implementation claim.  
**Scope:** read-only, single-domain natural-language → verified SHACL paths → Qwen structured plan → Python validation and deterministic SPARQL.  
**Phase 1 allowlist:** `RETRIEVE`, `COUNT`, `EXISTS`. Everything else is cataloged but **disabled**.

## Principles

1. **Primary operation** describes the requested result; **modifiers** describe restrictions or presentation. A query may combine multiple modifiers.
2. Qwen may choose only from the **runtime allowlist**, and may reference only candidate IDs and targets supplied by the verified schema registry. It must never supply predicate IRIs or SPARQL.
3. Python rejects unknown operations, unsupported combinations, invalid target IDs, unknown properties, incompatible operators/types, unsupported path expressions, and cross-domain requests. Unsupported requests are `UNRESOLVED`, not silently downgraded.
4. SHACL NodeShapes are **not automatically RDF classes**. Counts and existence checks require a verified binding pattern and explicit target variable; never invent `rdf:type`.
5. `WHERE` is SPARQL syntax, not a user intent; “where” may express a location target or a condition. “When” may request a date property or a temporal filter.
6. `DISTINCT`, `FILTER`, `GROUP BY`, `ORDER BY`, `LIMIT`, etc. are often **modifiers**, not independent primary intents.
7. Cataloging a capability does not mean the SHACL index, dataset, SPARQL endpoint, or current compiler supports it.
8. No `INSERT`, `DELETE`, `LOAD`, `CLEAR`, `DROP`, `CREATE`, `COPY`, `MOVE`, or `ADD` operations. This planner is read-only.

## A. Primary result intents

| ID | Intent | Meaning | SPARQL form | Phase |
|---|---|---|---|---|
| R01 | RETRIEVE | Return entities or property values | SELECT | **1** |
| R02 | COUNT | Count distinct target bindings | SELECT COUNT(DISTINCT …) | **1** |
| R03 | EXISTS | Test whether any binding satisfies a pattern | ASK | **1** |
| R04 | SUM | Sum numeric values | SUM | 3 |
| R05 | AVERAGE | Average numeric values | AVG | 3 |
| R06 | MINIMUM | Minimum numeric value | MIN | 3 |
| R07 | MAXIMUM | Maximum numeric value | MAX | 3 |
| R08 | SAMPLE | Return an arbitrary representative binding | SAMPLE | 4 |
| R09 | CONCATENATE | Combine grouped lexical values | GROUP_CONCAT | 4 |
| R10 | GROUPED_AGGREGATE | Aggregate per group | GROUP BY + aggregate | 3 |
| R11 | COMPARE | Compare two or more grounded targets | SELECT + expressions | 4 |
| R12 | DIFFERENCE | Compute numeric/date differences | BIND + expressions | 4 |
| R13 | RANK | Rank entities by a grounded property | ORDER BY + projection | 3 |
| R14 | TOP_K | Return highest-ranked K | ORDER BY DESC + LIMIT | 3 |
| R15 | BOTTOM_K | Return lowest-ranked K | ORDER BY ASC + LIMIT | 3 |
| R16 | CONSTRUCT_GRAPH | Return an RDF graph | CONSTRUCT | 5 |
| R17 | DESCRIBE_RESOURCE | Return implementation-defined resource description | DESCRIBE | 5 |
| R18 | ENUMERATE_RELATIONSHIPS | Return connected nodes/edges | SELECT | 4 |
| R19 | ENUMERATE_PROPERTIES | Return observed predicate/value pairs, where authorized | SELECT | 5 |
| R20 | EXPLAIN_PROVENANCE | Return graph/source metadata when modeled | SELECT + GRAPH | 5 |

## B. Selection and result modifiers

| ID | Modifier | Meaning | SPARQL feature | Phase |
|---|---|---|---|---|
| S01 | DISTINCT | Remove duplicate result rows/values | DISTINCT | 2 (compiler currently uses DISTINCT for retrieval) |
| S02 | REDUCED | Permit duplicate reduction | REDUCED | 5 |
| S03 | PROJECT_FIELDS | Select multiple grounded outputs | SELECT variables | 2 |
| S04 | ALIAS | Name computed outputs | AS | 3 |
| S05 | ORDER_ASC | Ascending ordering | ORDER BY ASC | 2 |
| S06 | ORDER_DESC | Descending ordering | ORDER BY DESC | 2 |
| S07 | LIMIT | Restrict result size | LIMIT | 2 |
| S08 | OFFSET | Skip initial results | OFFSET | 2 |
| S09 | GROUP_BY | Group results by grounded variables | GROUP BY | 3 |
| S10 | HAVING | Filter aggregated groups | HAVING | 3 |
| S11 | OPTIONAL | Keep rows with absent optional matches | OPTIONAL | 4 |
| S12 | UNION | Combine alternative graph patterns | UNION | 4 |
| S13 | SUBQUERY | Nested SELECT scope | sub-SELECT | 5 |
| S14 | BIND_EXPRESSION | Derive a value | BIND | 4 |
| S15 | VALUES_RESTRICTION | Restrict variable to explicit value set | VALUES | 3 |

## C. Value and attribute filters

| ID | Modifier | Meaning | SPARQL feature | Phase |
|---|---|---|---|---|
| F01 | EQUALS | Equal to typed literal/resource | FILTER = / pattern | 2 |
| F02 | NOT_EQUALS | Not equal | FILTER != | 2 |
| F03 | GREATER_THAN | Greater than | FILTER > | 2 |
| F04 | GREATER_OR_EQUAL | Greater than or equal | FILTER >= | 2 |
| F05 | LESS_THAN | Less than | FILTER < | 2 |
| F06 | LESS_OR_EQUAL | Less than or equal | FILTER <= | 2 |
| F07 | BETWEEN | Inclusive/exclusive range with explicit bounds | FILTER conjunction | 2 |
| F08 | IN_SET | Membership in finite typed set | IN / VALUES | 2 |
| F09 | NOT_IN_SET | Exclusion from finite set | NOT IN | 3 |
| F10 | CONTAINS_TEXT | Substring match | CONTAINS + STR | 2 |
| F11 | STARTS_WITH | Prefix match | STRSTARTS | 3 |
| F12 | ENDS_WITH | Suffix match | STRENDS | 3 |
| F13 | REGEX_MATCH | Regex with escaped user input and engine limits | REGEX | 4 |
| F14 | CASE_INSENSITIVE | Case-folded text comparison | LCASE/UCASE | 3 |
| F15 | LANGUAGE_MATCH | Language-tag restriction | LANG/LANGMATCHES | 4 |
| F16 | DATATYPE_MATCH | RDF literal datatype restriction | DATATYPE | 4 |
| F17 | IS_IRI | Require IRI-valued binding | isIRI | 4 |
| F18 | IS_LITERAL | Require literal binding | isLiteral | 4 |
| F19 | IS_BLANK | Require blank node | isBlank | 4 |
| F20 | IS_BOUND | Require bound variable | BOUND | 3 |
| F21 | IS_UNBOUND | Require absent optional value | !BOUND / NOT EXISTS | 4 |
| F22 | BOOLEAN_EQUALS | Match boolean value | FILTER | 2 |
| F23 | IDENTIFIER_MATCH | Match verified entity identifier | VALUES / FILTER | 2 |

## D. Logical and relationship constraints

| ID | Modifier | Meaning | SPARQL feature | Phase |
|---|---|---|---|---|
| L01 | AND | All conditions | && / joined patterns | 2 |
| L02 | OR | Any condition | || / UNION | 3 |
| L03 | NOT | Negate condition | ! | 3 |
| L04 | NESTED_LOGIC | Parenthesized compound conditions | FILTER expression | 4 |
| L05 | EXISTS_PATTERN | Require related pattern | FILTER EXISTS | 4 |
| L06 | NOT_EXISTS_PATTERN | Exclude related pattern | FILTER NOT EXISTS | 4 |
| L07 | MINUS_PATTERN | Subtract compatible solution mappings | MINUS | 5 |
| L08 | SAME_ENTITY | Bind conditions to same resource | shared variable | 3 |
| L09 | DIFFERENT_ENTITIES | Require distinct resource bindings | != / sameTerm | 4 |
| L10 | JOIN_BRANCHES | Join two verified branches at shared node | shared variable | 3 |
| L11 | INVERSE_RELATION | Traverse a verified inverse predicate | ^path / reversed triple | 4 |
| L12 | ALTERNATIVE_RELATION | Traverse verified alternatives | | property path / UNION | 4 |
| L13 | SEQUENCE_RELATION | Traverse verified ordered path | / property path / triples | 3 |
| L14 | ZERO_OR_MORE | Reachability, including zero hops | * property path | 5 |
| L15 | ONE_OR_MORE | Reachability, one or more hops | + property path | 5 |
| L16 | ZERO_OR_ONE | Optional single path step | ? property path | 5 |
| L17 | NEGATED_PROPERTY_SET | Traverse predicates except listed ones | ! property path | 5 |
| L18 | CYCLIC_TRAVERSAL | Traverse cycles with bounded policy | property path | 5 |
| L19 | SHORTEST_PATH | Shortest route in graph | engine-specific or external algorithm | Later |
| L20 | PATH_LENGTH | Number of edges in traversal | engine-specific / external | Later |

## E. Temporal intents and modifiers

| ID | Modifier | Meaning | SPARQL approach | Phase |
|---|---|---|---|---|
| T01 | RETURN_TIMESTAMP | Retrieve grounded date/time property | SELECT | 2 |
| T02 | BEFORE | Timestamp earlier than bound | typed comparison | 2 |
| T03 | AFTER | Timestamp later than bound | typed comparison | 2 |
| T04 | ON_DATE | Date equality / day interval | typed comparison | 2 |
| T05 | DATE_BETWEEN | Date/time interval | typed comparisons | 2 |
| T06 | EARLIEST | Minimum timestamp | MIN / ORDER BY | 3 |
| T07 | LATEST | Maximum timestamp | MAX / ORDER BY | 3 |
| T08 | RELATIVE_TIME | “last week”, “today” using explicit clock/timezone | normalized bounds | 4 |
| T09 | DATE_COMPONENT | Year/month/day/hour extraction | YEAR/MONTH/DAY/HOURS | 4 |
| T10 | DURATION | Difference between timestamps | datatype/engine-dependent | 5 |
| T11 | TIMEZONE | Explicit timezone interpretation | TZ/TIMEZONE, normalization | 5 |
| T12 | OVERLAPPING_INTERVALS | Interval overlap where modeled | multiple comparisons | 5 |
| T13 | EVENT_SEQUENCE | Order events by timestamps | ORDER BY + constraints | 5 |

## F. Graph, dataset, and specialized capabilities

| ID | Capability | Meaning | SPARQL approach | Phase |
|---|---|---|---|---|
| G01 | NAMED_GRAPH | Restrict to named graph | GRAPH | 5 |
| G02 | DATASET_SCOPE | Specify default/named graph dataset | FROM / FROM NAMED | 5 |
| G03 | SERVICE_FEDERATION | Query remote SPARQL service | SERVICE | Out of scope |
| G04 | CROSS_DOMAIN_JOIN | Traverse across domain boundaries | verified cross-domain joins | Out of scope |
| G05 | RDF_TYPE_FILTER | Match explicit verified RDF class | rdf:type | 4 |
| G06 | RDF_COLLECTION | Traverse RDF lists | rdf:first/rest | 5 |
| G07 | RDF_REIFICATION | Query statement metadata | reification/RDF-star support | Later |
| G08 | RDF_STAR | Query quoted triples if supported | implementation/version-dependent | Later |
| G09 | ONTOLOGY_INFERENCE | Use entailment rules | endpoint entailment regime | Later |
| G10 | TEXT_SEARCH | Full-text indexing | engine-specific | Later |
| G11 | GEOSPATIAL | Spatial predicates/distance | GeoSPARQL/engine-specific | Later |
| G12 | UNIT_CONVERSION | Normalize quantities with units | verified units + expressions | Later |
| G13 | CUSTOM_FUNCTION | Vendor-specific function calls | engine-specific | Later |
| G14 | PAGINATED_EXPORT | Iterate through result pages | LIMIT/OFFSET or cursor strategy | Later |
| G15 | SCHEMA_INTROSPECTION | Inspect available types/predicates | metadata SELECT | 5 |

## Phase 1: enforce a narrow runtime allowlist

```json
{
  "primary_operations": ["RETRIEVE", "COUNT", "EXISTS"],
  "modifiers": [],
  "domain_scope": "single-domain",
  "path_source": "verified SHACL registry",
  "query_author": "deterministic Python",
  "execution": "not in scope",
  "unsupported_behavior": "UNRESOLVED"
}
```

### Phase 1 Qwen plan contract (proposed; not yet implemented)

```json
{
  "status": "selected",
  "selected_candidate_ids": ["C2"],
  "operation": "COUNT",
  "target": {"candidate_id": "C2", "node_index": 2},
  "modifiers": [],
  "reason": "Count distinct EndPoint bindings"
}
```

- `status`: `selected`, `ambiguous`, or `unresolved`.
- `selected_candidate_ids`: only known candidate IDs, nonempty only when selected.
- `operation`: one of the three Phase 1 operations.
- `target`: reference to a verified node position or verified terminal property; for `COUNT` and `EXISTS` an entity target must be bound by verified traversal.
- `modifiers`: must be empty in Phase 1.
- `reason`: explanatory only; never used as executable input.
- Candidate paths ending at a **concept**, not just a property, must be supported before entity-only counts/existence can work.
- Compiler must reject unsupported SHACL path forms, invalid variable binding patterns, and ungrounded class assumptions.
- Qwen selection must not silently convert unsupported intent into `RETRIEVE`.

## Implementation checklist

- [x] Catalog complete initial inventory with phases and explicit out-of-scope items.
- [ ] Review intent names, edge cases, and phase allocations.
- [ ] Add concept-ending SHACL candidates.
- [ ] Add structured Qwen plan output for Phase 1.
- [ ] Validate operation, target binding, candidate IDs, and empty modifiers in Python.
- [ ] Compile Phase 1 `RETRIEVE`, `COUNT`, and `EXISTS` deterministically.
- [ ] Add offline positive/negative tests and real Ollama smoke tests.
- [ ] Validate generated queries against actual RDF storage and query engine.
