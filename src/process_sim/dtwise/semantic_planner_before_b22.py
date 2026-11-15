"""SHACL-grounded semantic query planner for DTwise.

Qwen selects a requested entity, path and supported intent from a bounded
catalog. Only schema-validated SHACL hops may become SPARQL predicates.
"""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dtwise.query_planner import validate_hops


def _labels(schema, uri):
    return list(schema.by_uri.get(uri, {}).get("labels", [])) if uri else []


def _candidates(schema, max_depth=5, max_candidates=160):
    candidates = []
    for concept in schema.concepts:
        if concept.get("kind") != "shape" or not concept.get("domain"):
            continue
        root, domain = concept["uri"], concept["domain"]
        # Discover root shapes from the schema, not question-specific keywords.
        # Accept domain-labelled and template-prefixed root shapes.
        labels = {str(x).casefold() for x in concept.get("labels", [])}
        domain_name = str(domain).casefold()
        
        if domain_name not in labels and f"tep_{domain_name}" not in labels:
            continue

        for hops in schema.shacl_paths(root, max_depth=max_depth, domain=domain):
            if not hops or hops[-1].get("to_shape") is None:
                continue
            if not validate_hops(hops, schema, root):
                continue

            end = hops[-1]["to_shape"]
            terminal = []
            for extension in schema.shacl_paths(end, max_depth=1, domain=domain):
                if (len(extension) != 1 or extension[0].get("to_shape") is not None
                        or not validate_hops(extension, schema, end)):
                    continue
                hop = extension[0]
                terminal.append({
                    "id": len(terminal),
                    "predicate": hop["property"],
                    "labels": _labels(schema, hop["property"]),
                    "_hop": hop,
                })

            candidates.append({
                "domain": domain,
                "root": root,
                "end": end,
                "target_labels": _labels(schema, end),
                "predicates": [h["property"] for h in hops],
                "path_steps": [
                    {
                        "predicate": h["property"],
                        "from_shape": h["from_shape"],
                        "to_shape": h["to_shape"],
                        "target_labels": _labels(schema, h["to_shape"]),
                    }
                    for h in hops
                ],
                "terminal": terminal,
                "_hops": hops,
            })

    # Keep each complete SHACL path distinct and deterministically ordered.
    unique = {}
    for candidate in candidates:
        key = (candidate["domain"], candidate["root"], candidate["end"],
               tuple(candidate["predicates"]))
        unique[key] = candidate
    ordered = sorted(unique.values(), key=lambda c: (
        c["domain"], len(c["predicates"]), tuple(c["predicates"]),
        c["root"], c["end"],
    ))
    if len(ordered) > max_candidates:
        raise ValueError(
            "SHACL candidate catalog too large; narrow the schema or increase catalog limit"
        )

    endpoints = sorted({(c["domain"], c["end"]) for c in ordered})
    endpoint_ids = {key: i for i, key in enumerate(endpoints)}
    for i, candidate in enumerate(ordered):
        candidate["id"] = i
        candidate["target_id"] = endpoint_ids[(candidate["domain"], candidate["end"])]
        candidate["children"] = [
            {
                "property": extension[0]["property"],
                "labels": _labels(schema, extension[0]["to_shape"]),
            }
            for extension in schema.shacl_paths(
                candidate["end"], max_depth=1, domain=candidate["domain"]
            )
            if len(extension) == 1 and extension[0].get("to_shape") is not None
            and validate_hops(extension, schema, candidate["end"])
        ]
    return ordered


def _domain_shortlist(question, catalog):
    """Use explicit schema-domain mentions, never a hardcoded domain vocabulary.

    Preserve original catalog IDs so downstream validation remains unchanged.
    If no domain is explicitly mentioned, do not guess one.
    """
    domains = sorted({c["domain"] for c in catalog})
    tokens = set(re.findall(r"[A-Za-z0-9_]+", question.casefold()))
    mentioned = [d for d in domains if d.casefold() in tokens]
    if len(mentioned) == 1:
        return [c for c in catalog if c["domain"] == mentioned[0]]
    if len(mentioned) > 1:
        raise ValueError("Question mentions multiple schema domains; disambiguation required")
    return catalog


def _concept_words(value):
    """Normalize schema labels and question phrases without domain vocabulary."""
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value))
    value = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", value)
    words = re.findall(r"[A-Za-z0-9]+", value.casefold())
    normalized = []
    for word in words:
        if len(word) > 3 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 2 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        normalized.append(word)
    return tuple(normalized)


def _label_spans(label, question_words):
    """Match a schema name against one or several question tokens.

    Supports CamelCase/compound names and simple plurals without using a
    domain-specific dictionary: EndPoint <-> endpoints / end points.
    """
    parts = _concept_words(label)
    if not parts:
        return []
    compact = "".join(parts)
    spans = []
    for start in range(len(question_words)):
        for end in range(start + 1, min(len(question_words), start + len(parts)) + 1):
            if "".join(question_words[start:end]) == compact:
                spans.append((start, end))
    return spans


def _concept_constraints(question, catalog):
    """Return named schema concepts and their last explicit text positions."""
    words = _concept_words(question)
    names = set()
    for candidate in catalog:
        for step in candidate["path_steps"]:
            if step["target_labels"]:
                names.add(step["target_labels"][0])
    return {name: max(end for _, end in spans)
            for name in names
            if (spans := _label_spans(name, words))}


def _candidate_matches_constraints(candidate, positions):
    """Ensure requested output is final and parent concepts occur before it."""
    if not positions:
        return True
    last = max(positions.values())
    targets = {name for name, position in positions.items() if position == last}
    steps = [step["target_labels"][0] if step["target_labels"] else None
             for step in candidate["path_steps"]]
    if not steps or steps[-1] not in targets:
        return False
    # Every explicitly mentioned schema concept must be represented along the
    # path, and text order must agree with path order when distinguishable.
    if not set(positions).issubset(set(steps)):
        return False
    return all(positions[a] <= positions[b]
               for a, b in zip(steps, steps[1:])
               if a in positions and b in positions)


def _concept_shortlist(question, catalog):
    """Select complete paths using named SHACL entities, never inferred joins.

    When no concepts are recognized, leave selection to the model. When
    concepts are recognized but no path fits, reject instead of degrading to
    an incorrect one-hop query.
    """
    positions = _concept_constraints(question, catalog)
    if not positions:
        return catalog
    matches = [candidate for candidate in catalog
               if _candidate_matches_constraints(candidate, positions)]
    if not matches:
        raise ValueError("No SHACL path matches the requested target and context")
    return matches


def _associated_property_request(question, catalog, schema):
    """Ground 'which PROPERTY are associated with ENTITY URI' to one SHACL shape.

    This is a narrowly parsed relational wording, not a domain-specific mapping:
    the output, identifier and traversal must all be present on one validated
    candidate. Ambiguous owners are rejected rather than arbitrarily selected.
    """
    match = re.fullmatch(
        r"\s*which\s+(?P<output>.+?)\s+are\s+associated\s+with\s+"
        r"(?:an?\s+|the\s+)?(?P<entity>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?P<identifier>https?://[^\s?]+)\??\s*", question, re.I)
    if not match:
        return None
    output_words = _concept_words(match.group("output"))
    entity_words = _concept_words(match.group("entity"))
    identifier = match.group("identifier").rstrip(".,;!?")
    if not output_words or not entity_words or not identifier:
        raise ValueError("Incomplete associated-property request")

    matches = []
    for candidate in _domain_shortlist(question, catalog):
        if not validate_hops(candidate["_hops"], schema, candidate["root"]):
            continue
        outputs = [p for p in candidate["terminal"]
                   if _group_property_matches(p, output_words)
                   and validate_hops([p["_hop"]], schema, candidate["end"])]
        # Entity name must match the leading words of a schema identifier
        # property (e.g. Asset + AssetIdentifier), not just an arbitrary URI.
        identifiers = [p for p in candidate["terminal"]
                       if any((_concept_words(label) == entity_words + ("identifier",))
                              for label in p["labels"])
                       and validate_hops([p["_hop"]], schema, candidate["end"])]
        if len(outputs) == 1 and len(identifiers) == 1:
            matches.append((candidate, outputs[0], identifiers[0]))
    if len(matches) != 1:
        raise ValueError("Associated-property request has no unique SHACL-validated owning path")
    candidate, output, filter_prop = matches[0]
    return {
        "query_type": "SELECT", "intent": "list", "domain": candidate["domain"],
        "target_variable": "entity", "predicates": candidate["predicates"],
        "start_shape": candidate["root"], "end_shape": candidate["end"],
        "evidence_ids": [e for hop in candidate["_hops"] for e in hop["evidence_ids"]],
        "planner": "shacl_associated_property", "target_id": candidate["target_id"],
        "target_labels": candidate["target_labels"],
        "projection": {"type": "terminal_property", "predicate": output["predicate"],
                       "from_shape": candidate["end"],
                       "evidence_ids": output["_hop"]["evidence_ids"]},
        "filters": {"op": "eq", "predicate": filter_prop["predicate"],
                    "from_shape": candidate["end"],
                    "evidence_ids": filter_prop["_hop"]["evidence_ids"],
                    "value": identifier},
        "validation_scope": "Verified SHACL structural triples; instance data not verified",
    }


def _possessive_property_request(question, catalog, schema):
    """Resolve 'For ENTITY URI, list its NOUN' only with unique SHACL evidence.

    A bare plural noun may refer to a terminal Name property only when the
    schema makes that interpretation unique. No domain vocabulary is embedded.
    """
    match = re.fullmatch(
        r"\s*for\s+(?:an?\s+|the\s+)?"
        r"(?P<entity>[A-Za-z][A-Za-z0-9_-]*)\s+"
        r"(?P<identifier>https?://[^\s,;]+)\s*,\s*"
        r"(?:list|show|get|retrieve|return|find)\s+"
        r"(?:its|their|the)\s+(?P<output>[A-Za-z][A-Za-z0-9_ -]*)"
        r"\s*[.!?]?\s*", question, re.I)
    if not match:
        return None
    entity_words = _concept_words(match.group("entity"))
    output_words = _concept_words(match.group("output"))
    identifier = match.group("identifier").rstrip(".!?")
    if not entity_words or not output_words or not identifier:
        raise ValueError("Incomplete possessive-property request")

    matches = []
    for candidate in _domain_shortlist(question, catalog):
        if not validate_hops(candidate["_hops"], schema, candidate["root"]):
            continue
        identifiers = [p for p in candidate["terminal"]
                       if _group_property_matches(p, entity_words + ("identifier",))
                       and validate_hops([p["_hop"]], schema, candidate["end"])]
        if len(identifiers) != 1:
            continue
        outputs = []
        for prop in candidate["terminal"]:
            if not validate_hops([prop["_hop"]], schema, candidate["end"]):
                continue
            # Prefer exact label; otherwise a generic NOUN -> NOUN Name
            # interpretation, e.g. 'signals' -> 'SignalName'.
            if (_group_property_matches(prop, output_words)
                    or _group_property_matches(prop, output_words + ("name",))):
                outputs.append(prop)
        if len(outputs) == 1 and outputs[0]["id"] != identifiers[0]["id"]:
            matches.append((candidate, outputs[0], identifiers[0]))
    if len(matches) != 1:
        raise ValueError("Possessive-property request has no unique SHACL-validated interpretation")
    candidate, output, filter_prop = matches[0]
    return {
        "query_type": "SELECT", "intent": "list", "domain": candidate["domain"],
        "target_variable": "entity", "predicates": candidate["predicates"],
        "start_shape": candidate["root"], "end_shape": candidate["end"],
        "evidence_ids": [e for hop in candidate["_hops"] for e in hop["evidence_ids"]],
        "planner": "shacl_possessive_property", "target_id": candidate["target_id"],
        "target_labels": candidate["target_labels"],
        "projection": {"type": "terminal_property", "predicate": output["predicate"],
                       "from_shape": candidate["end"],
                       "evidence_ids": output["_hop"]["evidence_ids"]},
        "filters": {"op": "eq", "predicate": filter_prop["predicate"],
                    "from_shape": candidate["end"],
                    "evidence_ids": filter_prop["_hop"]["evidence_ids"],
                    "value": identifier},
        "validation_scope": "Verified SHACL structural triples; instance data not verified",
    }


def _group_property_matches(prop, requested_words):
    """Match a grouping label on its owning SHACL shape, not globally."""
    labels = list(prop.get("labels", []))
    # A schema may expose only the RDF predicate, with no friendly label.
    labels.append(prop["predicate"].rsplit("/", 1)[-1].rsplit("#", 1)[-1])
    for label in labels:
        normalized = _concept_words(label)
        if normalized == requested_words:
            return True
        # hasAssetIdentifier -> AssetIdentifier (generic RDF naming convention).
        if normalized and normalized[0] == "has" and normalized[1:] == requested_words:
            return True
        if str(label).startswith("has") and _concept_words(str(label)[3:]) == requested_words:
            return True
    return False


def _grouped_count_request(question, catalog):
    """Parse a grouping role; resolve its predicate only after entity selection."""
    # Aggregate-threshold listing: the requested output is the grouping key,
    # while the noun following the threshold is the counted SHACL entity.
    having = re.fullmatch(
        r"\s*(?:list|show|find|return|get|retrieve)\s+(?:the\s+)?"
        r"(?P<group>[A-Za-z][A-Za-z0-9_]*)\s+with\s+"
        r"(?P<comparison>more than|greater than|over|fewer than|less than|at least|at most)\s+"
        r"(?P<amount>[0-9]+|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?P<entity>[A-Za-z][A-Za-z0-9_]*)\s*[.?!]*\s*", question, re.I)
    if having:
        words = {"zero": 0, "one": 1, "two": 2, "three": 3,
                 "four": 4, "five": 5, "six": 6, "seven": 7,
                 "eight": 8, "nine": 9, "ten": 10}
        token = having.group("amount").lower()
        amount = int(token) if token.isdigit() else words[token]
        if amount > 1000000000:
            raise ValueError("Aggregate threshold is out of range")
        op = {"more than": ">", "greater than": ">", "over": ">",
              "fewer than": "<", "less than": "<", "at least": ">=",
              "at most": "<="}[having.group("comparison").lower()]
        return ("Count " + having.group("entity") + ".",
                _concept_words(having.group("group")),
                {"function": "count", "operator": op, "value": amount})
    if not re.match(r"\s*(?:count|how many|number of)\b", question, re.I):
        return None
    match = re.search(r"\b(?:for|by)\s+(?:each|every)\s+(.+?)\s*[.?!]*$", question, re.I)
    if not match:
        return None
    requested_words = _concept_words(match.group(1))
    if not requested_words:
        raise ValueError("Empty grouping property")
    return question[:match.start()].rstrip() + ".", requested_words, None


def _requested_terminal_properties(question, catalog):
    """Find explicitly named terminal properties using schema labels only."""
    words = _concept_words(question)
    found = {}
    for candidate in catalog:
        for prop in candidate["terminal"]:
            labels = [label for label in prop["labels"]
                      if not str(label).casefold().startswith("has")]
            if any(_label_spans(label, words) for label in labels):
                found[prop["predicate"]] = True
    return set(found)


def _explicit_output_property_ids(question, candidate):
    """Ground coordinated output names to SHACL properties, without ontology templates.

    Only the leading request clause is considered; property names in a WHERE
    clause or in entity context cannot silently become output projections.
    Ambiguous schema-label matches fail closed.
    """
    if not re.match(r"\s*(?:get|show|list|retrieve|return|find)\b", question, re.I):
        return []
    prefix = re.split(r"\b(?:where|whose|with|having|from|for|of)\b", question,
                      maxsplit=1, flags=re.I)[0]
    words = _concept_words(prefix)
    occurrences = {}
    for prop in candidate["terminal"]:
        for label in prop["labels"]:
            if str(label).casefold().startswith("has"):
                continue
            for start, end in _label_spans(label, words):
                occurrences.setdefault((start, end), set()).add(prop["id"])
    if any(len(ids) != 1 for ids in occurrences.values()):
        raise ValueError("Ambiguous output property labels on selected SHACL shape")
    ordered = sorted((start, end, next(iter(ids)))
                     for (start, end), ids in occurrences.items())
    result = []
    for start, end, pid in ordered:
        if pid not in result:
            result.append(pid)
    return result


def _requested_output_label(question, domains=()):
    """Capture an explicitly requested output label, not an ontology mapping."""
    match = re.match(r"\s*(?:get|show|list|retrieve|return|find)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9_]*)\b", question, re.I)
    if not match:
        return None
    token = match.group(1)
    if token.casefold() in {"all", "each", "every", "distinct", "number", "count"} or token.casefold() in {str(domain).casefold() for domain in domains}:
        return None
    return token


def _matches_property_label(token, prop):
    words = _concept_words(token)
    return any(_concept_words(label) == words for label in prop["labels"]
               if not str(label).casefold().startswith("has"))


def _required_equality(question, candidate):
    """Recognize equality syntax only for labels grounded on the selected shape."""
    for prop in candidate["terminal"]:
        for label in prop["labels"]:
            if str(label).casefold().startswith("has"):
                continue
            words = _concept_words(label)
            name = r"\s*".join(map(re.escape, words))
            # Accept CamelCase as well as separated spelling.
            names = [re.escape(str(label)), name]
            for name_pattern in names:
                pattern = (r"(?:where|with|whose|and|have|has)\s" + name_pattern +
                           r"\s+(?:is\s+|=\s*|equals\s+|equal\s+to\s+)" +
                           r"[\"']?([^\s,;\"']+)")
                match = re.search(pattern, question, re.I)
                if match:
                    value = match.group(1).rstrip(".?!)")
                    if value and value.casefold() not in {"is", "equals", "to"}:
                        return prop["predicate"], value
    return None



def _explicit_equalities(question, candidate):
    """Find simple chains of explicit equality clauses and their connectors.

    Repeated properties are allowed (e.g. assetIdentifier=A or
    assetIdentifier=B). Return empty for expressions we cannot safely parse.
    """
    matches = []
    for prop in candidate["terminal"]:
        for label in prop["labels"]:
            if str(label).casefold().startswith("has"):
                continue
            words = _concept_words(label)
            patterns = {re.escape(str(label)), r"\s*".join(map(re.escape, words))}
            for name in patterns:
                pattern = (r"\b" + name +
                           r"\s+(?:is\s+|=\s*|equals\s+|equal\s+to\s+)" +
                           r"[\"']?([^\s,;\"']+)")
                for m in re.finditer(pattern, question, re.I):
                    value = m.group(1).rstrip(".?! )")
                    if value:
                        matches.append((m.start(), m.end(), prop["id"], value, prop["predicate"]))
    # Different labels can refer to the same occurrence. Keep a single
    # interpretation only if all aliases resolve to the same property/value.
    by_span = {}
    for match in matches:
        key = (match[0], match[1])
        if key in by_span and by_span[key][2:] != match[2:]:
            return [], []
        by_span[key] = match
    matches = sorted(by_span.values())
    if len(matches) < 2:
        return matches, []
    connectors = []
    for left, right in zip(matches, matches[1:]):
        between = question[left[1]:right[0]].strip()
        if not re.fullmatch(r"(?:and|or)", between, re.I):
            return [], []
        connectors.append(between.casefold())
    return matches, connectors


def _ollama(question, catalog, host, model, timeout):
    public = [
        {
            "id": c["id"],
            "domain": c["domain"],
            "target_id": c["target_id"],
            "target_labels": c["target_labels"],
            "path": c["predicates"],
            "path_steps": c["path_steps"],
            "contained_entities": c["children"],
            "properties": [
                {"id": p["id"], "labels": p["labels"], "predicate": p["predicate"]}
                for p in c["terminal"]
            ],
        }
        for c in catalog
    ]
    system = (
        "You select a semantic query PLAN, not a catalog entry. "
        "Return only the fields required by the JSON schema; NEVER copy a catalog object. "
        "candidate_id is the selected catalog item's id, not its target_id. "
        "Choose the requested OUTPUT entity as the FINAL path endpoint. "
        "Use all contextual entities in the question to select the intermediate path steps. "
        "For example, if a question asks for endpoints belonging to devices, the path "
        "must traverse the device before reaching the endpoint, not a different parent. "
        "This is a general path-context rule, not a domain-specific exception. "
        "Inspect path_steps in sequence, not just target_labels. "
        "A parent or container is not the requested child. "
        "Only select IDs in the supplied catalog; return the matching target_id. "
        "For an entity list use intent=list; for a count use intent=count. "
        "A requested output property is not a condition filter. " "Select projection_property_id for a requested output property, independently of condition_property_id. " "Both may be present, including the same property. " 
        "For ordinary listing or counting without a property filter, set "
        "condition_property_id=null, operator=null, and value=null. "
        "Use operator=exists only when requesting entities HAVING a property, "
        "and supply a valid condition_property_id. "
        "Use operator=equals when the question explicitly supplies an equality value, whether quoted or unquoted. "
        "If a terminal property is requested, choose its owning entity path; "
        "the caller projects the schema-validated property value. "
        "If unsupported or ambiguous, set candidate_id=-1 and target_id=-1, "
        "intent=list, and all optional fields to null. "
        "For exactly one output property use projection_property_id and set projection_property_ids=null. "
        "For multiple output properties use projection_property_ids in output order and set projection_property_id=null. "
        "Classify each mentioned property by its role: requested output, filter, or both. "
        "A coordinated list of output properties requires multiple projections in output order. "
        "Prepositions and conjunctions do not express equality constraints by themselves. "
        "Never turn an output property into a filter without an explicit condition. "
        "For two or more conditions you MUST return filter_ir, never just one legacy condition. "
        "Preserve Boolean logic EXACTLY: when the question says OR, use op=or, never op=and; "
        "when it says AND, use op=and, never op=or. "
        "For example, assetIdentifier is FI103 or assetIdentifier is FI104 means "
        "filter_ir={op:or,children:[{op:eq,property_id:ID,value:FI103},{op:eq,property_id:ID,value:FI104}]}. "
        "For multiple conditions return filter_ir as a nested tree: group nodes have op=and/or and children; "
        "leaf nodes have op=eq/exists/not_exists/contains and property_id, with value for eq/contains. "
        "Use only catalog property IDs, and preserve values exactly as supplied. "
        "If filter_ir is supplied, set legacy condition_property_id/operator/value to null. "
        "If projection_property_ids is supplied, set legacy projection_property_id to null. "
        "Do not invent a join or unsupported relationship. "
    )
    response_schema = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "integer"},
            "target_id": {"type": "integer"},
            "intent": {"type": "string", "enum": ["list", "count"]},
            "projection_property_id": {"type": ["integer", "null"]},
            "projection_property_ids": {"type": ["array", "null"], "items": {"type": "integer"}},
            "filter_ir": {"type": ["object", "null"]},
            "condition_property_id": {"type": ["integer", "null"]},
            "operator": {"type": ["string", "null"], "enum": ["exists", "equals", None]},
            "value": {"type": ["string", "null"]},
        },
        "required": ["candidate_id", "target_id", "intent",
                     "projection_property_id", "projection_property_ids", "filter_ir",
                      "condition_property_id", "operator", "value"],
        "additionalProperties": False,
    }
    payload = {
        "model": model,
        "stream": False,
        "format": response_schema,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"question": question, "catalog": public})},
        ],
    }
    request = Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            reply = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValueError("Qwen/Ollama request failed: " + str(exc)) from exc
    try:
        return json.loads(reply["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Qwen did not return a valid JSON plan") from exc


def _ordered_property_request(question):
    """Recognize explicit value ordering and a bounded top-N request."""
    numbers = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
               "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    match = re.fullmatch(
        r"\s*(?:get|show|list|retrieve|return|find)\s+(?:the\s+)?"
        r"(?:first|top)\s+(?P<number>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?P<property>[A-Za-z][A-Za-z0-9_]*)\s+"
        r"in\s+(?:(?:ascending|descending)\s+)?alphabetical\s+order\s*[.!?]?\s*",
        question, re.I)
    if not match:
        return None
    token = match.group("number").casefold()
    count = int(token) if token.isdigit() else numbers[token]
    if not 1 <= count <= 1000:
        raise ValueError("Requested result limit must be 1..1000")
    descending = bool(re.search(r"\bdescending\s+alphabetical\b", question, re.I))
    return _concept_words(match.group("property")), count, ("desc" if descending else "asc")


def _plan_ordered_property(question, schema, catalog):
    """Build a fully SHACL-verified ordered terminal-value plan."""
    request = _ordered_property_request(question)
    if request is None:
        return None
    words, count, direction = request
    matches = []
    for candidate in _domain_shortlist(question, catalog):
        for prop in candidate["terminal"]:
            if (_group_property_matches(prop, words)
                    and validate_hops(candidate["_hops"], schema, candidate["root"])
                    and validate_hops([prop["_hop"]], schema, candidate["end"])):
                matches.append((candidate, prop))
    # Never select an arbitrary domain or path for a property with multiple owners.
    if len(matches) != 1:
        raise ValueError("Ordered output property has no unique SHACL-verified owning path")
    candidate, prop = matches[0]
    return {
        "query_type": "SELECT", "intent": "list", "domain": candidate["domain"],
        "target_variable": "entity", "start_shape": candidate["root"],
        "end_shape": candidate["end"], "predicates": candidate["predicates"],
        "evidence_ids": [e for hop in candidate["_hops"] for e in hop["evidence_ids"]],
        "projection": {"type": "terminal_property", "predicate": prop["predicate"],
                       "from_shape": candidate["end"], "evidence_ids": prop["_hop"]["evidence_ids"]},
        "ordered_values": {"direction": direction, "distinct": True, "limit": count},
        "planner": "shacl_ordered_property", "target_labels": candidate["target_labels"],
        "validation_scope": "Verified SHACL structural triples; instance data not verified",
    }


def plan_question_semantic(question, paths, schema, *,
                           host="http://localhost:11434",
                           model="qwen2.5-coder:3b", timeout=60, interpret=None):
    """Build a plan from SHACL evidence. `paths` retained for caller compatibility."""
    catalog = _candidates(schema)
    if not catalog:
        raise ValueError("No SHACL root-to-entity candidates available")
    possessive_plan = _possessive_property_request(question, catalog, schema)
    if possessive_plan is not None:
        return possessive_plan

    associated_plan = _associated_property_request(question, catalog, schema)
    if associated_plan is not None:
        return associated_plan

    ordered_plan = _plan_ordered_property(question, schema, catalog)
    if ordered_plan is not None:
        return ordered_plan

    from dtwise.cross_domain_join import plan_join
    cross_domain_plan = plan_join(question, catalog, schema)
    if cross_domain_plan is not None:
        return cross_domain_plan

    domain_shortlist = _domain_shortlist(question, catalog)
    grouped_request = _grouped_count_request(question, domain_shortlist)
    # The grouping key is a terminal property, not a traversal target.
    entity_question = grouped_request[0] if grouped_request else question
    shortlist = _concept_shortlist(entity_question, domain_shortlist)
    if grouped_request:
        # Restrict to entities that actually own the grouping terminal property.
        # Multiple paths to the same endpoint remain distinct and validated.
        shortlist = [c for c in shortlist if any(
            _group_property_matches(p, grouped_request[1]) for p in c["terminal"])]
        if not shortlist:
            raise ValueError("No counted entity has the requested SHACL grouping property")
    # Projection and filter roles are chosen independently by Qwen.  Schema
    # labels below are only used as a coverage guard, never to infer roles.
    mentioned_properties = _requested_terminal_properties(entity_question, domain_shortlist)
    requested_property = None
    # A broad target query can legitimately describe several SHACL routes.
    # Never let an LLM silently choose a subset of those routes.
    positions = _concept_constraints(entity_question, domain_shortlist)
    same_target = len({(c["domain"], tuple(_concept_words(c["target_labels"][0]))
                       if c["target_labels"] else ()) for c in shortlist}) == 1
    same_root = len({(c["domain"], c["root"]) for c in shortlist}) == 1
    broad_target = (bool(positions) and len(positions) == 1
                    and len(shortlist) > 1 and same_target and same_root)
    if broad_target and not mentioned_properties and not grouped_request:
        # Ask Qwen for intent/conditions, not authority to select a path.
        # A property condition cannot be applied safely to heterogeneous routes
        # without separately validating it on every endpoint shape.
        choice = (interpret(question, shortlist) if interpret is not None
                  else _ollama(question, shortlist, host, model, timeout))
        if (not isinstance(choice, dict) or choice.get("intent") not in ("list", "count")
                or choice.get("operator") is not None
                or choice.get("condition_property_id") is not None
                or choice.get("value") is not None):
            raise ValueError("Multi-path target query has unsupported or ambiguous conditions")
        if any(not validate_hops(c["_hops"], schema, c["root"]) for c in shortlist):
            raise ValueError("Multi-path query includes a non-SHACL-validated route")
        branches = []
        for c in shortlist:
            branch = {"predicates": c["predicates"], "end_shape": c["end"],
                      "evidence_ids": [e for h in c["_hops"] for e in h["evidence_ids"]],
                      "candidate_id": c["id"], "target_labels": c["target_labels"]}
            if requested_property is not None:
                prop = next((p for p in c["terminal"]
                             if p["predicate"] == requested_property), None)
                if prop is None or not validate_hops([prop["_hop"]], schema, c["end"]):
                    raise ValueError("UNION branch lacks verified terminal-property evidence")
                branch["projection"] = {
                    "type": "terminal_property", "predicate": prop["predicate"],
                    "from_shape": c["end"], "evidence_ids": prop["_hop"]["evidence_ids"]}
            branches.append(branch)
        if os.environ.get("DTWISE_PLANNER_DEBUG", "").lower() in ("1", "true", "yes"):
            print("=== SEMANTIC PLANNER DEBUG ===", flush=True)
            print("Full catalog size:", len(catalog), flush=True)
            print("Domain shortlist IDs:", [c["id"] for c in domain_shortlist], flush=True)
            print("Concept shortlist IDs:", [c["id"] for c in shortlist], flush=True)
            print("Multi-path UNION IDs:", [c["id"] for c in shortlist], flush=True)
            print("Qwen intent:", choice["intent"], flush=True)
            print("================================", flush=True)
        return {
            "query_type": "SELECT", "intent": choice["intent"],
            "domain": shortlist[0]["domain"], "target_variable": "entity",
            "start_shape": shortlist[0]["root"], "end_shape": None,
            "predicates": [], "evidence_ids": [],
            "branches": branches,
            **({"projection": {"type": "terminal_property", "predicate": requested_property}}
               if requested_property is not None else {}),
            "planner": "qwen_shacl_multi_path",
            "target_labels": shortlist[0]["target_labels"],
            "validation_scope": "Each UNION branch verified against SHACL structural triples; instance data not verified",
        }
    if len(shortlist) > 1 and positions and len(positions) == 1 and same_target and not same_root:
        raise ValueError("Target has multiple incompatible SHACL roots; clarification required")
    choice = (interpret(question, shortlist) if interpret is not None
              else _ollama(question, shortlist, host, model, timeout))
    if os.environ.get("DTWISE_PLANNER_DEBUG", "").lower() in ("1", "true", "yes"):
        print("=== SEMANTIC PLANNER DEBUG ===", flush=True)
        print("Full catalog size:", len(catalog), flush=True)
        print("Domain shortlist IDs:", [c["id"] for c in domain_shortlist], flush=True)
        print("Concept shortlist IDs:", [c["id"] for c in shortlist], flush=True)
        print("Qwen raw choice:", repr(choice), flush=True)
        print("Requested output label:", _requested_output_label(question, {c["domain"] for c in shortlist}), flush=True)
        print("================================", flush=True)
    if not isinstance(choice, dict) or "error" in choice:
        raise ValueError("Qwen rejected or could not disambiguate the question")

    # A uniquely constrained SHACL candidate is authoritative.
    # Do not let the LLM independently assign its target entity ID.
    if len(shortlist) == 1:
        choice = {
            **choice,
            "candidate_id": shortlist[0]["id"],
            "target_id": shortlist[0]["target_id"],
        }
    
    candidate_id = choice.get("candidate_id")
    if type(candidate_id) is not int or candidate_id not in {c["id"] for c in shortlist}:
        raise ValueError("Qwen selected an invalid or out-of-domain candidate ID")
    if choice.get("intent") not in ("list", "count"):
        raise ValueError("Qwen selected an unsupported intent")

    candidate = catalog[candidate_id]
    if type(choice.get("target_id")) is not int:
        raise ValueError("Qwen did not identify a target entity type")
    if choice["target_id"] != candidate["target_id"]:
        # Qwen sometimes puts the selected terminal projection's *local* ID
        # into target_id. Correct only that specific, SHACL-grounded mistake.
        # The property must be explicitly named in the question and valid on
        # this candidate; unrelated target mismatches still fail closed.
        projection_id = choice.get("projection_property_id")
        explicit_properties = _requested_terminal_properties(question, [candidate])
        projection_is_explicit_and_valid = (
            type(projection_id) is int
            and choice["target_id"] == projection_id
            and 0 <= projection_id < len(candidate["terminal"])
            and candidate["terminal"][projection_id]["predicate"] in explicit_properties
            and validate_hops([candidate["terminal"][projection_id]["_hop"]],
                              schema, candidate["end"])
        )
        if not projection_is_explicit_and_valid:
            raise ValueError("Semantic target/path mismatch: path ends at a different entity type")
        choice["target_id"] = candidate["target_id"]

    # Recheck the chosen complete path against explicit target/context labels.
    # Never treat successful SPARQL execution as proof of semantic correctness.
    constraints = _concept_constraints(entity_question, domain_shortlist)
    if not _candidate_matches_constraints(candidate, constraints):
        raise ValueError("Selected path does not match requested target and context")

    if os.environ.get("DTWISE_PLANNER_DEBUG", "").lower() in ("1", "true", "yes"):
        print("Qwen choice:", json.dumps(choice, indent=2), flush=True)
        print("Selected target:", json.dumps(candidate["target_labels"]), flush=True)
        print("Selected path:", json.dumps(candidate["predicates"]), flush=True)
        print("Selected steps:", json.dumps(candidate["path_steps"], indent=2), flush=True)

    hops = candidate["_hops"]
    if not validate_hops(hops, schema, candidate["root"]):
        raise ValueError("Selected path failed SHACL validation")
    evidence = [e for hop in hops for e in hop["evidence_ids"]]
    plan = {
        "query_type": "SELECT",
        "intent": choice["intent"],
        "domain": candidate["domain"],
        "target_variable": "entity",
        "predicates": candidate["predicates"],
        "start_shape": candidate["root"],
        "end_shape": candidate["end"],
        "evidence_ids": evidence,
        "planner": "qwen_shacl",
        "target_id": candidate["target_id"],
        "target_labels": candidate["target_labels"],
        "validation_scope": "Verified SHACL structural triples; instance data not verified",
    }

    if grouped_request:
        if choice["intent"] != "count" and grouped_request[2] is None:
            raise ValueError("Grouped count requires count intent")
        if grouped_request[2] is not None:
            # The explicit aggregate threshold, not the listing verb, defines intent.
            choice = {**choice, "intent": "count", "operator": None,
                      "condition_property_id": None, "value": None,
                      "filter_ir": None, "projection_property_id": None,
                      "projection_property_ids": None}
        if choice["intent"] != "count":
            raise ValueError("Grouped count requires count intent")
        # The plan was constructed before the explicit HAVING request
        # normalized the LLM's listing intent to aggregate count intent.
        # Keep the emitted plan consistent with that validated operation.
        plan["intent"] = "count"
        matches = [p for p in candidate["terminal"]
                   if _group_property_matches(p, grouped_request[1])
                   and validate_hops([p["_hop"]], schema, candidate["end"])]
        if len(matches) != 1:
            raise ValueError("Grouping property is not SHACL-validated on counted entity")
        prop = matches[0]
        plan["group_by"] = [{
            "type": "terminal_property", "predicate": prop["predicate"],
            "from_shape": candidate["end"],
            "evidence_ids": prop["_hop"]["evidence_ids"]}]
        plan["aggregation"] = {"function": "count", "distinct": True,
                               "target_variable": "entity"}
        if grouped_request[2] is not None:
            plan["having"] = grouped_request[2]

    # Recover explicitly coordinated output properties using only selected
    # SHACL terminal labels. This is a generic semantic-role consistency check,
    # not a benchmark-question or ontology-specific template.
    requested_output_ids = _explicit_output_property_ids(question, candidate)
    if len(requested_output_ids) >= 2:
        if len(requested_output_ids) > 12:
            raise ValueError("Too many requested output properties")
        for pid in requested_output_ids:
            if not validate_hops([candidate["terminal"][pid]["_hop"]],
                                 schema, candidate["end"]):
                raise ValueError("Requested output lacks SHACL evidence")
        # A multi-output question may also contain genuine constraints; keep
        # them intact. Only remove an LLM-invented equality when the question
        # has no explicit equality and no filter/condition clause whatsoever.
        if (choice.get("operator") == "equals"
                and not _explicit_equalities(question, candidate)[0]
                and not re.search(r"\b(?:where|whose|with|having)\b", question, re.I)
                and choice.get("filter_ir") is None):
            choice = {**choice, "condition_property_id": None,
                      "operator": None, "value": None}
            plan["condition_resolution"] = "unsupported_equality_removed"
        choice = {**choice, "projection_property_id": None,
                  "projection_property_ids": requested_output_ids}
        plan["projection_resolution"] = "explicit_output_shacl_recovery"

    # Normalize a redundant legacy projection only when it exactly matches
    # the sole structured projection. Conflicting selections still fail closed.
    structured_projection_ids = choice.get("projection_property_ids")
    legacy_projection_id = choice.get("projection_property_id")
    if (isinstance(structured_projection_ids, list)
            and len(structured_projection_ids) == 1
            and type(structured_projection_ids[0]) is int
            and type(legacy_projection_id) is int
            and structured_projection_ids[0] == legacy_projection_id):
        choice = {**choice, "projection_property_id": None}

    # Structured semantic IR: projections are independent of conditions.
    projection_ids = choice.get("projection_property_ids")
    if projection_ids is not None:
        if (not isinstance(projection_ids, list) or not projection_ids
                or len(projection_ids) > 12 or len(set(map(str, projection_ids))) != len(projection_ids)
                or choice.get("projection_property_id") is not None):
            raise ValueError("Invalid structured projection selection")
        validated = []
        for pid in projection_ids:
            if type(pid) is not int or not 0 <= pid < len(candidate["terminal"]):
                raise ValueError("Invalid structured projection property ID")
            prop = candidate["terminal"][pid]
            if not validate_hops([prop["_hop"]], schema, candidate["end"]):
                raise ValueError("Structured projection lacks SHACL evidence")
            validated.append({"type": "terminal_property", "predicate": prop["predicate"],
                              "from_shape": candidate["end"], "evidence_ids": prop["_hop"]["evidence_ids"]})
        plan["projections"] = validated
        plan["projection"] = validated[0]  # compatibility with existing consumers
    projection_id = choice.get("projection_property_id")
    if projection_id is not None:
        if type(projection_id) is not int or not 0 <= projection_id < len(candidate["terminal"]):
            raise ValueError("Qwen selected an invalid projection property ID")
        prop = candidate["terminal"][projection_id]
        if not validate_hops([prop["_hop"]], schema, candidate["end"]):
            raise ValueError("Selected projection failed SHACL validation")
        plan["projection"] = {
            "type": "terminal_property", "predicate": prop["predicate"],
            "from_shape": candidate["end"],
            "evidence_ids": prop["_hop"]["evidence_ids"],
        }

    # Fail closed if an explicitly requested output property is not the
    # selected projection. This also prevents plausible-but-wrong substitutions
    # for unsupported or cross-domain output properties.
    output_label = (None if grouped_request and grouped_request[2] is not None
                    else _requested_output_label(question, {candidate["domain"]}))
    if output_label is not None:
        matching = [p for p in candidate["terminal"]
                    if _matches_property_label(output_label, p)]
        if matching:
            if not any(p["predicate"] in {m["predicate"] for m in matching}
                       for p in plan.get("projections", [plan.get("projection")]) if p):
                raise ValueError("Semantic output coverage failure: requested property not projected")
        elif plan.get("projection") is not None and not plan.get("projections"):
            raise ValueError("Unsupported output property on selected SHACL entity: " + output_label)

    if requested_output_ids:
        projected = {p["predicate"] for p in
                     (plan.get("projections") or [plan.get("projection")]) if p}
        # In a grouped aggregation the grouping key is selected as ?group0,
        # not as a conventional ?value0 terminal-property projection.
        # Only count SHACL-validated group keys as output coverage.
        if grouped_request:
            projected |= {p["predicate"] for p in plan.get("group_by", [])}
        missing = {candidate["terminal"][pid]["predicate"]
                   for pid in requested_output_ids} - projected
        if missing:
            raise ValueError("Semantic output coverage failure: requested output omitted")

    # A bounded, schema-grounded repair for an omitted equality selection.
    # Qwen still chooses the entity and projection. Only recover a condition
    # explicitly present in the question and uniquely matched to a verified
    # terminal property of that same selected entity. Never override a
    # conflicting non-null Qwen condition or guess a missing value.
    required_equality = _required_equality(question, candidate)
    if (required_equality is not None and choice.get("filter_ir") is None
            and choice.get("operator") is None
            and choice.get("condition_property_id") is None
            and choice.get("value") in (None, required_equality[1])):
        required_predicate, required_value = required_equality
        matches = [p for p in candidate["terminal"]
                   if p["predicate"] == required_predicate
                   and validate_hops([p["_hop"]], schema, candidate["end"])]
        if len(matches) == 1:
            choice = {**choice, "operator": "equals",
                      "condition_property_id": matches[0]["id"],
                      "value": required_value}
            plan["condition_resolution"] = "explicit_equality_shacl_recovery"

    # For an unambiguous flat chain, deterministically preserve the user's
    # connective. Repair a missing or wrong model filter only when the chain
    # is homogeneous (all AND or all OR), and every equality is grounded.
    # Mixed or nested expressions are not rewritten: fail closed below if
    # they cannot be verified.
    explicit, connectors = _explicit_equalities(question, candidate)
    if len(explicit) >= 2 and connectors and len(set(connectors)) == 1:
        requested_op = connectors[0]
        expected_leaves = [
            {"op": "eq", "property_id": item[2], "value": item[3]}
            for item in explicit
        ]
        selected_ir = choice.get("filter_ir")
        if selected_ir is None:
            legacy_id = choice.get("condition_property_id")
            legacy_op = choice.get("operator")
            legacy_value = choice.get("value")
            if legacy_op is not None and not any(
                legacy_id == item[2] and legacy_op == "equals"
                and legacy_value == item[3] for item in explicit
            ):
                raise ValueError("Qwen condition conflicts with explicit equalities")
            if legacy_op is None and (legacy_id is not None or legacy_value is not None):
                raise ValueError("Incomplete legacy condition in multi-filter query")
            choice = {**choice, "condition_property_id": None,
                      "operator": None, "value": None,
                      "filter_ir": {"op": requested_op, "children": expected_leaves}}
            plan["condition_resolution"] = "explicit_multi_equality_shacl_recovery"
        else:
            # Do not allow an LLM to silently change OR to AND (or vice versa).
            # For a flat, homogeneous chain, the normalized exact tree is
            # fully determined by the user's clauses and SHACL property IDs.
            def same_flat_clauses(ir):
                if not isinstance(ir, dict) or ir.get("op") not in ("and", "or"):
                    return False
                children = ir.get("children")
                if not isinstance(children, list) or len(children) != len(expected_leaves):
                    return False
                actual = []
                for child in children:
                    if not isinstance(child, dict) or child.get("op") != "eq":
                        return False
                    actual.append((child.get("property_id"), child.get("value")))
                expected = [(item["property_id"], item["value"]) for item in expected_leaves]
                return sorted(actual, key=str) == sorted(expected, key=str)
            if same_flat_clauses(selected_ir):
                if selected_ir["op"] != requested_op:
                    choice = {**choice, "filter_ir": {"op": requested_op,
                                                       "children": expected_leaves}}
                    plan["condition_resolution"] = "explicit_boolean_operator_correction"
            else:
                raise ValueError("Structured filter conflicts with explicit Boolean equalities")
    elif len(explicit) >= 2 and connectors:
        # Mixed AND/OR requires a fully validated Boolean parser; never
        # silently accept an arbitrary tree as equivalent.
        raise ValueError("Mixed AND/OR equality expressions are not yet supported safely")

    filter_ir = choice.get("filter_ir")
    if filter_ir is not None:
        # Qwen may duplicate a structured leaf in the legacy condition fields.
        # Remove only a provably identical duplicate; never discard a distinct
        # condition or silently reinterpret a Boolean expression.
        legacy = (choice.get("operator"), choice.get("condition_property_id"),
                  choice.get("value"))
        if any(item is not None for item in legacy):
            legacy_op, legacy_pid, legacy_value = legacy
            expected_op = {"equals": "eq", "exists": "exists"}.get(legacy_op)
            def contains_identical_leaf(node):
                if not isinstance(node, dict):
                    return False
                if node.get("op") in ("and", "or"):
                    children = node.get("children")
                    return (isinstance(children, list)
                            and any(contains_identical_leaf(child) for child in children))
                return (expected_op is not None
                        and node.get("op") == expected_op
                        and type(legacy_pid) is int
                        and node.get("property_id") == legacy_pid
                        and (node.get("value") == legacy_value if expected_op == "eq"
                             else legacy_value is None and node.get("value") is None))
            if not contains_identical_leaf(filter_ir):
                raise ValueError("Cannot mix non-equivalent legacy condition with structured filter IR")
            choice = {**choice, "operator": None,
                      "condition_property_id": None, "value": None}
            plan["condition_resolution"] = "equivalent_legacy_filter_deduplicated"
        def ground_filter(node, depth=0):
            if not isinstance(node, dict) or depth > 5:
                raise ValueError("Invalid filter IR node/depth")
            op = node.get("op")
            if op in ("and", "or"):
                if set(node) != {"op", "children"} or not isinstance(node["children"], list) or not 1 <= len(node["children"]) <= 8:
                    raise ValueError("Invalid compound filter group")
                children = [ground_filter(child, depth+1) for child in node["children"]]
                # A one-child boolean group is equivalent to its validated child.
                return children[0] if len(children) == 1 else {"op": op, "children": children}
            if op not in ("eq", "exists", "not_exists", "contains") or set(node) - {"op", "property_id", "value"}:
                raise ValueError("Unsupported structured filter operator")
            pid = node.get("property_id")
            if type(pid) is not int or not 0 <= pid < len(candidate["terminal"]):
                raise ValueError("Invalid structured filter property ID")
            prop = candidate["terminal"][pid]
            if not validate_hops([prop["_hop"]], schema, candidate["end"]):
                raise ValueError("Structured filter lacks SHACL evidence")
            out = {"op": op, "predicate": prop["predicate"], "from_shape": candidate["end"],
                   "evidence_ids": prop["_hop"]["evidence_ids"]}
            if op in ("eq", "contains"):
                value = node.get("value")
                if not isinstance(value, str) or not 1 <= len(value) <= 200 or any(ord(c) < 32 for c in value) or value.casefold() not in question.casefold():
                    raise ValueError("Structured filter value must occur verbatim in question")
                out["value"] = value
            elif "value" in node:
                raise ValueError("Existence filter cannot carry value")
            return out
        def strip_nulls(node):
            if not isinstance(node, dict): return node
            return {k: ([strip_nulls(c) for c in v] if k == "children" and isinstance(v, list) else v)
                    for k, v in node.items() if v is not None}
        plan["filters"] = ground_filter(strip_nulls(filter_ir))
    operator = choice.get("operator")
    property_id = choice.get("condition_property_id")
    value = choice.get("value")
    if operator is None:
        if property_id is not None or value is not None:
            raise ValueError("Inconsistent condition fields")
    elif operator in ("exists", "equals"):
        if type(property_id) is not int or not 0 <= property_id < len(candidate["terminal"]):
            raise ValueError("Qwen selected an invalid property ID")
        prop = candidate["terminal"][property_id]
        if not validate_hops([prop["_hop"]], schema, candidate["end"]):
            raise ValueError("Selected condition failed SHACL validation")
        plan["condition"] = {
            "type": "lexical_equals" if operator == "equals" else "exists_property",
            "predicate": prop["predicate"],
            "from_shape": candidate["end"],
            "evidence_ids": prop["_hop"]["evidence_ids"],
        }
        if operator == "equals":
            if (not isinstance(value, str) or not 1 <= len(value) <= 200
                    or any(ord(char) < 32 for char in value)):
                raise ValueError("Invalid equality value")
            # Do not invent a value: it must appear verbatim in the question.
            if value.casefold() not in question.casefold():
                raise ValueError("Comparison value was not supplied in the question")
            plan["condition"]["value"] = value
        elif value is not None:
            raise ValueError("Existence query cannot carry a value")
    else:
        raise ValueError("Unsupported operator")
    if required_equality is not None and filter_ir is None:
        predicate, required_value = required_equality
        actual = plan.get("condition")
        if (not actual or actual.get("type") != "lexical_equals"
                or actual.get("predicate") != predicate
                or actual.get("value", "").casefold() != required_value.casefold()):
            raise ValueError("Semantic filter coverage failure: required equality omitted or changed")
    if len(explicit) >= 2:
        def equality_leaves(node):
            if not node:
                return set()
            if "children" in node:
                return set().union(*(equality_leaves(c) for c in node["children"]))
            if node.get("op") == "eq":
                return {(node["predicate"], node["value"])}
            return set()
        expected = {(item[4], item[3]) for item in explicit}
        if not expected.issubset(equality_leaves(plan.get("filters"))):
            raise ValueError("Semantic filter coverage failure: explicit equalities omitted")

    covered = {p["predicate"] for p in (plan.get("projections") or [plan.get("projection")]) if p}
    if plan.get("condition"):
        covered.add(plan["condition"]["predicate"])
    def filter_predicates(node):
        if not node: return set()
        if "children" in node: return set().union(*(filter_predicates(c) for c in node["children"]))
        return {node["predicate"]}
    covered |= filter_predicates(plan.get("filters"))
    covered |= {p["predicate"] for p in plan.get("group_by", [])}
    if mentioned_properties - covered:
        raise ValueError("Semantic coverage failure: requested property omitted from projection/filter")
    return plan

