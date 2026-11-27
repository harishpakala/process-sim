"""Compile SAFSL existsExactlyOne/matches contracts into SHACL-SPARQL.

This module deliberately requires explicit RDF bindings and authoritative
completeness metadata; it does not infer mappings from AAS idShort strings.
The emitted shapes validate a complete snapshot. The runtime admission
decision (V/F/U/NA) is the responsibility of the caller.
"""

# Created: 2026-10-31
# Author: Harish
import base64
import binascii
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Mapping

from lark import Lark, Transformer
from rdflib import BNode, Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import SH

SELIRA = Namespace("https://example.org/selira/contracts#")


class CompilationError(ValueError):
    pass


@dataclass(frozen=True)
class TemplateRef:
    alias: str
    identifier: str


@dataclass(frozen=True)
class UniqueRule:
    focus_variable: str
    focus_alias: str
    product_variable: str
    product_alias: str
    left_variable: str
    left_field: str
    right_variable: str
    right_field: str


@dataclass(frozen=True)
class MatchRule:
    focus_variable: str
    focus_alias: str
    left_variable: str
    left_field: str
    right_variable: str
    right_field: str


@dataclass(frozen=True)
class Contract:
    identifier: str
    rule: UniqueRule | MatchRule


@dataclass(frozen=True)
class Specification:
    name: str
    templates: tuple
    contracts: tuple


class _ContractTransformer(Transformer):
    def NAME(self, token):
        return str(token)

    def STRING(self, token):
        return json.loads(str(token))

    def field(self, items):
        return tuple(items)

    def template_ref(self, items):
        return TemplateRef(*items)

    def unique_rule(self, items):
        return tuple(items)

    def match_rule(self, items):
        return tuple(items)

    def forall_rule(self, items):
        focus_var, focus_alias, rule = items
        if len(rule) == 2:
            left, right = rule
            if left[0] != focus_var or right[0] != focus_var:
                raise CompilationError("Standalone matches requires two fields of the focus variable")
            return MatchRule(focus_var, focus_alias, *left, *right)
        product_var, product_alias, left, right = rule
        return UniqueRule(focus_var, focus_alias, product_var,
                          product_alias, *left, *right)

    def contract(self, items):
        return Contract(*items)

    def start(self, items):
        return Specification(items[0],
                             tuple(x for x in items[1:] if isinstance(x, TemplateRef)),
                             tuple(x for x in items[1:] if isinstance(x, Contract)))


def parse_contract(source: str) -> Specification:
    grammar = files("process_sim.safsl").joinpath("grammar/contracts.lark").read_text(encoding="utf-8")
    parser = Lark(grammar, parser="lalr", start="start")
    try:
        return _ContractTransformer().transform(parser.parse(source))
    except Exception as exc:
        raise CompilationError(f"Invalid SAFSL contract: {exc}") from exc


def decode_template_id(value: str) -> str:
    """Decode existing SAFSL Base64 convention; reject malformed/noncanonical encodings."""
    try:
        raw = base64.b64decode(value, validate=True)
        decoded = raw.decode("utf-8")
        if not decoded or base64.b64encode(raw).decode("ascii") != value:
            raise ValueError("noncanonical or empty template ID")
        return decoded
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise CompilationError(f"Invalid Base64 AAS template identifier: {value!r}") from exc


def _iri(value, label):
    if not isinstance(value, str) or not (value.startswith("http://") or value.startswith("https://") or value.startswith("urn:")):
        raise CompilationError(f"{label} must be an absolute HTTP(S) or URN IRI")
    if any(c in value for c in (' ', '<', '>', '"', '\n', '\r')):
        raise CompilationError(f"Unsafe characters in {label}")
    return URIRef(value)


def _compile_match(graph, spec, contract, aliases):
    rule = contract.rule
    try:
        focus_id, focus = aliases[rule.focus_alias]
        cls = _iri(focus["class"], "focus class")
        left = _iri(focus["fields"][rule.left_field], "left field")
        right = _iri(focus["fields"][rule.right_field], "right field")
    except (KeyError, TypeError) as exc:
        raise CompilationError(f"Unresolved match binding: {exc}") from exc
    policy = focus.get("comparison_policy", {})
    if policy.get("kind") not in ("normalized_asset_identifier", "lexical_equality"):
        raise CompilationError("Unsupported standalone comparison policy")
    if policy["kind"] == "lexical_equality" and policy.get("exceptions"):
        raise CompilationError("Lexical equality does not support exceptions")
    exceptions = policy.get("exceptions", [])
    from .identifier_comparison import identifier_matches
    clauses = []
    for pair in exceptions:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(x, str) for x in pair):
            raise CompilationError("Invalid identifier exception pair")
        local, asset = pair
        identifier_matches(local, asset)
        clauses.append(f"(STR(?local) = {Literal(local).n3()} && STR(?asset) = {Literal(asset).n3()})")
    comparison = 'REPLACE(STR(?local), "[_-]", "") = REPLACE(REPLACE(STR(?asset), "^.*/", ""), "[_-]", "")'
    if clauses:
        comparison = "(" + comparison + " || " + " || ".join(clauses) + ")"
    query = f"""SELECT $this WHERE {{
      $this <{left}> ?local ; <{right}> ?asset .
      FILTER (!(REGEX(STR(?local), "^[A-Za-z0-9_-]+$")
        && REGEX(STR(?asset), "^https?://[^/?#]+/([^?#]*/)?[A-Za-z0-9_-]+$")
        && STRLEN(REPLACE(STR(?local), "[_-]", "")) > 0
        && STRLEN(REPLACE(REPLACE(STR(?asset), "^.*/", ""), "[_-]", "")) > 0
        && ({comparison})))
    }}"""
    if policy["kind"] == "lexical_equality":
        query = f"SELECT $this WHERE {{ $this <{left}> ?local ; <{right}> ?asset . FILTER (STR(?local) != STR(?asset)) }}"
    shape = SELIRA[f"{spec.name}_{contract.identifier}"]
    graph.add((shape, RDF.type, SH.NodeShape))
    if focus.get("target_by_predicate"):
        graph.add((shape, SH.targetSubjectsOf, right))
    else:
        graph.add((shape, SH.targetClass, cls))
    for predicate in (left, right):
        prop = BNode()
        graph.add((shape, SH.property, prop))
        graph.add((prop, SH.path, predicate))
        graph.add((prop, SH.minCount, Literal(1)))
        graph.add((prop, SH.maxCount, Literal(1)))
    sparql = BNode()
    graph.add((shape, SH.sparql, sparql))
    graph.add((sparql, RDF.type, SH.SPARQLConstraint))
    graph.add((sparql, SH.message, Literal(f"{contract.identifier}: inconsistent local and authoritative identifiers")))
    graph.add((sparql, SH.select, Literal(query)))
    return {
        "id": contract.identifier, "shape": str(shape),
        "kind": "standalone_match", "focus_template_id": focus_id,
        "focus_class": str(cls), "focus_predicate": str(right),
        "left_predicate": str(left), "right_predicate": str(right),
        "comparison_policy": policy, "dependencies": [focus_id],
        "requires_complete": [focus_id],
        "runtime_evidence_complete": bool(focus.get("complete")),
    }


def compile_contract(source: str, bindings: Mapping):
    """Return (Turtle string, JSON-serializable manifest).

    bindings format:
    {"templates": {
       "<decoded AAS template ID>": {
          "class": "<RDF class IRI>",
          "fields": {"productRef": "<predicate IRI>"},
          "complete": true
       }
    }}
    Each focus and catalog template must be explicitly bound. Completeness
    is recorded for runtime admission; it is not proved by this compiler.
    """
    spec = parse_contract(source)
    aliases = {}
    for ref in spec.templates:
        if ref.alias in aliases:
            raise CompilationError(f"Duplicate template alias: {ref.alias}")
        template_id = decode_template_id(ref.identifier)
        info = bindings.get("templates", {}).get(template_id)
        if not isinstance(info, dict):
            raise CompilationError(f"No RDF mapping for AAS template {template_id}")
        aliases[ref.alias] = (template_id, info)

    graph = Graph()
    graph.bind("sh", SH)
    graph.bind("selira", SELIRA)
    manifest = {"specification": spec.name, "contracts": []}
    for contract in spec.contracts:
        rule = contract.rule
        if isinstance(rule, MatchRule):
            manifest["contracts"].append(_compile_match(graph, spec, contract, aliases))
            continue
        if rule.focus_alias not in aliases or rule.product_alias not in aliases:
            raise CompilationError(f"{contract.identifier}: unknown template alias")
        if (rule.left_variable, rule.right_variable) != (rule.focus_variable, rule.product_variable):
            raise CompilationError(f"{contract.identifier}: matches() operands must be focus.field, product.field")
        focus_id, focus = aliases[rule.focus_alias]
        product_id, product = aliases[rule.product_alias]
        try:
            focus_class = _iri(focus["class"], "focus class")
            product_class = _iri(product["class"], "product class")
            focus_pred = _iri(focus["fields"][rule.left_field], "focus field")
            product_pred = _iri(product["fields"][rule.right_field], "product field")
        except (KeyError, TypeError) as exc:
            raise CompilationError(f"{contract.identifier}: unresolved semantic binding: {exc}") from exc

        # No variable IRI interpolation except validated RDF URIRef N3 serialization.
        # Distinct RDF resources are counted as distinct canonical entities;
        # the graph must normalize owl:sameAs before evaluation.
        match1 = "STR(?ref) = STR(?id)" if product.get("lexical_match") else "?ref = ?id"
        match2 = "STR(?ref1) = STR(?id1) && STR(?ref2) = STR(?id2)" if product.get("lexical_match") else "?ref1 = ?id1 && ?ref2 = ?id2"
        catalog_pattern = (f"?product <{product_pred}> ?id ." if product.get("match_by_predicate") else f"?product a <{product_class}> ; <{product_pred}> ?id .")
        p1_pattern = (f"?p1 <{product_pred}> ?id1 ." if product.get("match_by_predicate") else f"?p1 a <{product_class}> ; <{product_pred}> ?id1 .")
        p2_pattern = (f"?p2 <{product_pred}> ?id2 ." if product.get("match_by_predicate") else f"?p2 a <{product_class}> ; <{product_pred}> ?id2 .")
        query = f"""SELECT $this WHERE {{
  FILTER (
    NOT EXISTS {{
      $this <{focus_pred}> ?ref .
      {catalog_pattern}
      FILTER ({match1})
    }}
    ||
    EXISTS {{
      $this <{focus_pred}> ?ref1 .
      {p1_pattern}
      $this <{focus_pred}> ?ref2 .
      {p2_pattern}
      FILTER (?p1 != ?p2 && {match2})
    }}
  )
}}"""
        shape = SELIRA[f"{spec.name}_{contract.identifier}"]
        sparql = BNode()
        graph.add((shape, RDF.type, SH.NodeShape))
        if focus.get("target_by_predicate"):
            graph.add((shape, SH.targetSubjectsOf, focus_pred))
        else:
            graph.add((shape, SH.targetClass, focus_class))
        graph.add((shape, SH.sparql, sparql))
        graph.add((sparql, RDF.type, SH.SPARQLConstraint))
        graph.add((sparql, SH.message, Literal(f"{contract.identifier}: exactly one canonical product required")))
        graph.add((sparql, SH.select, Literal(query)))
        manifest["contracts"].append({
            "id": contract.identifier,
            "shape": str(shape),
            "focus_template_id": focus_id,
            "catalog_template_id": product_id,
            "focus_class": str(focus_class),
            "catalog_class": str(product_class),
            "focus_predicate": str(focus_pred),
            "catalog_predicate": str(product_pred),
            "dependencies": [focus_id, product_id],
            "requires_complete": [focus_id, product_id],
            "runtime_evidence_complete": bool(focus.get("complete") and product.get("complete")),
            "identity_policy": "distinct RDF resources; canonicalize equivalent entities before validation",
        })
    return graph.serialize(format="turtle"), manifest



def export_sparql(ttl: str, manifest: Mapping, output_dir):
    """Export exact SHACL queries and standalone violation queries.

    Standalone export supports the compiler's current target and constraint
    fragment, including minCount/maxCount property constraints.
    """
    graph = Graph().parse(data=ttl, format="turtle")
    root = Path(output_dir)
    for entry in manifest["contracts"]:
        shape = URIRef(entry["shape"])
        name = entry["id"].replace("_", "-")
        targets = []
        for predicate in graph.objects(shape, SH.targetSubjectsOf):
            targets.append(f"?this {predicate.n3()} ?targetValue .")
        for cls in graph.objects(shape, SH.targetClass):
            targets.append(f"?this <{RDF.type}>/<http://www.w3.org/2000/01/rdf-schema#subClassOf>* {cls.n3()} .")
        if not targets:
            raise CompilationError("SPARQL export requires an explicit supported target")
        target = " UNION ".join("{ " + t + " }" for t in targets)
        queries = sorted(str(q) for constraint in graph.objects(shape, SH.sparql)
                         for q in graph.objects(constraint, SH.select))
        branches = []
        for index, query in enumerate(queries, 1):
            suffix = "" if len(queries) == 1 else f"-{index}"
            out = root / "shacl"
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{name}{suffix}.rq").write_text(query + "\n", encoding="utf-8")
            header = "SELECT $this WHERE {"
            if not query.startswith(header) or not query.rstrip().endswith("}"):
                raise CompilationError("Unsupported generated SPARQL query structure")
            body = query[len(header):].rstrip()[:-1]
            branches.append("{ { " + target + " } " + body + " }")
        for prop in graph.objects(shape, SH.property):
            predicate = graph.value(prop, SH.path)
            if not isinstance(predicate, URIRef):
                raise CompilationError("Unsupported property path for SPARQL export")
            minimum = graph.value(prop, SH.minCount)
            maximum = graph.value(prop, SH.maxCount)
            if minimum is not None:
                branches.append("{ { " + target + " } FILTER NOT EXISTS { SELECT ?this WHERE { ?this "
                    + predicate.n3() + " ?value . } GROUP BY ?this HAVING (COUNT(DISTINCT ?value) >= "
                    + str(int(minimum)) + ") } }" if int(minimum) > 0 else "{ FILTER(false) }")
            if maximum is not None:
                branches.append("{ { SELECT ?this WHERE { ?this " + predicate.n3()
                    + " ?value . } GROUP BY ?this HAVING (COUNT(DISTINCT ?value) > "
                    + str(int(maximum)) + ") } }")
        if not branches:
            raise CompilationError("No supported constraints to export")
        standalone = "SELECT DISTINCT ?this WHERE {\n  { " + target + " }\n  {\n    " + "\n    UNION ".join(branches) + "\n  }\n}\n"
        out = root / "standalone"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.rq").write_text(standalone, encoding="utf-8")


def compile_files(source_path, bindings_path, output_dir):
    source = Path(source_path).read_text(encoding="utf-8")
    bindings = json.loads(Path(bindings_path).read_text(encoding="utf-8"))
    ttl, manifest = compile_contract(source, bindings)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "integrity_shapes.ttl").write_text(ttl, encoding="utf-8")
    (out / "contract_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    export_sparql(ttl, manifest, out / "sparql")
    return manifest


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Compile SAFSL integrity contracts to SHACL")
    p.add_argument("source")
    p.add_argument("bindings")
    p.add_argument("output_dir")
    args = p.parse_args()
    print(json.dumps(compile_files(args.source, args.bindings, args.output_dir), indent=2))
