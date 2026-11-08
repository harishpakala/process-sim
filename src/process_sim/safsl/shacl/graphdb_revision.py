"""Read-only GraphDB revision fingerprints for SC-01 evidence.

Fingerprints detect observed changes, not authoritative version tokens.
Two independent SPARQL reads are NOT an atomic GraphDB snapshot. This module
must not be used as proof of distributed compare-and-swap.
"""

# Created: 2026-10-31
# Author: Harish
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from selira_integration.graphdb_snapshot import AI, PC, _iri, select, snapshot_from_rows


@dataclass(frozen=True)
class ObservedEvidence:
    snapshot: object
    fingerprints: dict[str, str]


def _fingerprint(rows, keys):
    canonical = sorted(tuple(row[key] for key in keys) for row in rows)
    return hashlib.sha256(json.dumps(canonical, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def observe(endpoint, inventory_graph, catalog_graph, *, complete=False, select_fn=None):
    """Read both named graphs and return deterministic content fingerprints.

    Source identifiers are lexical RDF values, matching the existing
    lifecycle SC-01 evaluator. No completeness or revision authority inferred.
    """
    select_fn = select if select_fn is None else select_fn
    inv, cat = _iri(inventory_graph), _iri(catalog_graph)
    assets = select_fn(endpoint, f"""PREFIX ai: <{AI}>
SELECT ?asset ?ref WHERE {{ GRAPH {inv} {{
 ?asset ai:hasProductReference ?ref .
}} }} ORDER BY ?asset ?ref""")
    products = select_fn(endpoint, f"""PREFIX pc: <{PC}>
SELECT ?product ?identifier WHERE {{ GRAPH {cat} {{
 ?product pc:hasAssetIdentifier ?identifier .
}} }} ORDER BY ?product ?identifier""")
    fingerprints = {
        inventory_graph: _fingerprint(assets, ("asset", "ref")),
        catalog_graph: _fingerprint(products, ("product", "identifier")),
    }
    snapshot = snapshot_from_rows(
        fingerprints[inventory_graph] + ":" + fingerprints[catalog_graph],
        assets, products, complete=complete
    )
    return ObservedEvidence(snapshot, fingerprints)


def verify_unchanged(observed, endpoint, inventory_graph, catalog_graph, *, select_fn=None):
    """Re-read both sources; fail closed if content changed or read fails.

    Even a matching result cannot eliminate races after this check.
    """
    try:
        current = observe(endpoint, inventory_graph, catalog_graph,
                          complete=observed.snapshot.complete, select_fn=select_fn)
    except Exception:
        return False
    return current.fingerprints == observed.fingerprints
