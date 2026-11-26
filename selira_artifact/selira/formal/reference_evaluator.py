"""Direct AST interpretation of the TEP lexical uniqueness fragment."""
import base64
from rdflib import RDF, URIRef
from selira.language.parser.contracts import parse_contract

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
