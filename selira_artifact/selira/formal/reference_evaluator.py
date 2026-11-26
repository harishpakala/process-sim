"""Direct AST interpretation of lexical uniqueness and standalone matches."""
import base64
from rdflib import RDF, URIRef
from selira.language.parser.contracts import parse_contract
from selira.language.ast.contracts import MatchRule
from selira.formal.identifier_comparison import identifier_matches

def _evaluate_match(rule, binding, graph):
    policy = binding.get("comparison_policy", {})
    if policy.get("kind") != "normalized_asset_identifier":
        raise ValueError("Unsupported comparison policy")
    left = URIRef(binding["fields"][rule.left_field])
    right = URIRef(binding["fields"][rule.right_field])
    nodes = (set(graph.subjects(right, None)) if binding.get("target_by_predicate")
             else set(graph.subjects(RDF.type, URIRef(binding["class"]))))
    exceptions = {tuple(pair) for pair in policy.get("exceptions", [])}
    rows = {}
    for node in nodes:
        local = set(graph.objects(node, left))
        asset = set(graph.objects(node, right))
        valid = False
        if len(local) == len(asset) == 1:
            try:
                valid = identifier_matches(str(next(iter(local))),
                                           str(next(iter(asset))),
                                           exceptions=exceptions)
            except ValueError:
                pass
        rows[str(node)] = {"conforms": valid,
                           "local_ids": sorted(map(str, local)),
                           "asset_identifiers": sorted(map(str, asset))}
    return rows


def evaluate(source, bindings, graph):
    spec = parse_contract(source)
    aliases = {}
    for ref in spec.templates:
        if ref.alias in aliases:
            raise ValueError("Duplicate alias")
        identifier = base64.b64decode(ref.identifier, validate=True).decode("utf-8")
        aliases[ref.alias] = bindings["templates"][identifier]
    results = {}
    for contract in spec.contracts:
        r = contract.rule
        if isinstance(r, MatchRule):
            results[contract.identifier] = _evaluate_match(r, aliases[r.focus_alias], graph)
            continue
        if (r.left_variable, r.right_variable) != (r.focus_variable, r.product_variable):
            raise ValueError("Unsupported operands")
        s, t = aliases[r.focus_alias], aliases[r.product_alias]
        if not s.get("target_by_predicate") or not t.get("lexical_match") or t.get("match_by_predicate"):
            raise ValueError("Unsupported binding mode")
        fp, tp, tc = URIRef(s["fields"][r.left_field]), URIRef(t["fields"][r.right_field]), URIRef(t["class"])
        targets = set(graph.subjects(RDF.type, tc))
        rows = {}
        for node in set(graph.subjects(fp, None)):
            refs = {str(v) for v in graph.objects(node, fp)}
            matches = sorted(str(p) for p in targets if refs.intersection(str(v) for v in graph.objects(p, tp)))
            rows[str(node)] = {"matches": matches, "cardinality": len(matches)}
        results[contract.identifier] = rows
    return results
