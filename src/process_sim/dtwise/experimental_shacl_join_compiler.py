"""Phase 4.5: deterministic, read-only SPARQL for two verified sibling paths.

No question interpretation, model call, query execution, or ECAD assumptions.
"""
from process_sim.dtwise.experimental_shacl_join_topology import verified_shared_ancestor
from process_sim.dtwise.experimental_shacl_sparql import _iri


def compile_verified_sibling_join(qualified, result_ids):
    """Compile two property projections sharing a verified ancestor.

    Output variables are ?value1 and ?value2 in result_ids order.
    Root-to-ancestor triples are emitted once; branches stay independent.
    """
    topology = verified_shared_ancestor(qualified, result_ids)
    paths = [qualified["registry"][rid] for rid in result_ids]
    shared_count = len(topology["shared_node_uris"])
    lines = []
    for i, edge in enumerate(topology["shared_edges"]):
        lines.append(f"  ?n{i} {_iri(edge['predicate'])} ?n{i+1} .")
    ancestor_var = f"?n{shared_count-1}"
    for branch_number, path in enumerate(paths, 1):
        current = ancestor_var
        for i, edge in enumerate(path["edges"][shared_count-1:], shared_count):
            next_var = f"?b{branch_number}_{i}"
            lines.append(f"  {current} {_iri(edge['predicate'])} {next_var} .")
            current = next_var
        lines.append(
            f"  {current} {_iri(path['property']['predicate'])} ?value{branch_number} .")
    return "SELECT DISTINCT ?value1 ?value2 WHERE {\n" + "\n".join(lines) + "\n}"
