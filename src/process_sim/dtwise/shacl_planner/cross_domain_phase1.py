"""Standalone cross-domain Phase-1 planning: one Qwen call, approved joins only.

Reuses single-domain candidate retrieval, operation contract, and mapping graph.
No SPARQL generation or execution.
"""
from __future__ import annotations

import json
import re
import time

from process_sim.dtwise.shacl_planner.mapping_intent import explicit_shared_key, restrict_shared_key

from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    _prune_explicit_candidates, compact_n_domain_prompt,
)
from process_sim.dtwise.experimental_shacl_cross_domain_graph import (
    qualify_mapping_graph, validate_mapping_graph_selection,
)
from process_sim.dtwise.shacl_planner.multi_domain.cross_domain_mappings import (
    load_cross_domain_mappings,
)
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import (
    SYSTEM_PROMPT, _schema_anchors, _explicit_filter_property_names,
    _unsupported_intent, _explicit_limit, _explicit_sort, _constraint_literals,
    build_candidates, normalize_property_only_projections, validate_output,
    _explicit_shacl_comparisons,
)

CROSS_DOMAIN_PROMPT = """Select a SHACL-grounded cross-domain plan using only offered IDs.
Return exactly one JSON object with these keys:
{
 "status":"selected",
 "projection_ids":[],
 "existence_ids":[],
 "filters":[],
 "boolean_operator":"NONE",
 "count_target_id":null,
 "order_by":[],
 "limit":null,
 "mapping_ids":[],
 "reason":""
}
projection_ids: IDs of requested outputs (R entities or P properties).
existence_ids: R IDs only, for required entities not returned or counted.
mapping_ids: approved mapping IDs connecting the requested owners and domains.
Python derives identifier endpoints and join fields; do not output them.
For a request to show both matching entities, project both R IDs and use
existence_ids=[] and filters=[] unless a literal condition is explicitly stated.
A shared identifier is a join, NOT a literal filter or existence constraint.
filters: objects with property_id (P ID), operator (=, !=, >, >=, <, <=),
and value (literal string copied from the question). Include every explicit
comparison; never invent values or use candidate IDs as literal values.
boolean_operator: NONE for zero or one filter, AND or OR as requested otherwise.
count_target_id: R ID of the entity counted, or null. Do not project or add
the count target to existence_ids for a count-only request.
order_by: objects with property_id and direction (ASC or DESC).
limit: explicitly requested positive integer, otherwise null.
If a request cannot be represented, return unresolved, ambiguous or unsupported
with empty arrays, null count/limit, NONE, and a nonempty reason.
Never invent properties, mappings or paths. No extra keys.
"""


def _construct_cross_domain_plan(selection, graph, registry, exact_shapes):
    """Expand the compact model contract without silently dropping extra fields."""
    if not isinstance(selection, dict):
        raise ValueError('Selection must be a JSON object')
    expected = {'status', 'projection_ids', 'existence_ids', 'filters',
                'boolean_operator', 'count_target_id', 'order_by', 'limit',
                'mapping_ids', 'reason'}
    if set(selection) != expected:
        raise ValueError('Invalid compact cross-domain selection fields')
    answer = {**selection, 'identifier_path_ids': [], 'join_owner_id': None,
              'join': False}
    return _derive_unique_mapping_endpoints(answer, graph, registry, exact_shapes)


def _scoped_candidates(domain, qualified):
    registry = qualified['registry']
    candidates = []
    for candidate in qualified['prompt']['candidates']:
        local = candidate['id']
        source = registry.get(local, {})
        candidates.append({
            **candidate, 'id': f'{domain}:{local}', 'domain': domain,
            'node_uris': source.get('node_uris', []),
        })
    return candidates







def _normalize_explicit_sort_and_placeholder_filters(answer, candidates, question):
    """Ground explicit sort ownership; discard only invented placeholder filters."""
    if answer.get('status') != 'selected':
        return answer
    comparisons = _explicit_shacl_comparisons(question, candidates)
    filters = answer.get('filters')
    if not comparisons and isinstance(filters, list):
        placeholder = re.compile(r'^<[^<>]+>$')
        kept = [
            f for f in filters
            if not (isinstance(f, dict)
                    and isinstance(f.get('value'), str)
                    and placeholder.fullmatch(f['value'].strip()))
        ]
        if len(kept) != len(filters):
            answer['filters'] = kept
            if len(kept) <= 1:
                answer['boolean_operator'] = 'NONE'

    orders = answer.get('order_by')
    if not isinstance(orders, list) or len(orders) != 1:
        return answer
    order = orders[0]
    if not isinstance(order, dict):
        return answer
    sort_clause = re.search(
        r'\b(?:order(?:ed|ing)?|sort(?:ed|ing)?)\b(.+)',
        question, re.I)
    if sort_clause:
        clause = sort_clause.group(1)
        matches = []
        for c in candidates:
            if c.get('kind') != 'property':
                continue
            parts = c.get('path', '').split(' → ')
            if len(parts) < 3:
                continue
            owner, prop = parts[-2], parts[-1]
            domain = c.get('domain', '')
            pattern = (r'(?<!\w)' + re.escape(domain) + r'\s+'
                       + re.escape(owner) + r'\s+' + re.escape(prop)
                       + r'(?!\w)')
            if re.search(pattern, clause, re.I):
                matches.append(c['id'])
        if len(matches) == 1:
            order['property_id'] = matches[0]
    if re.search(
        r'\b(?:desc|descending|highest\s+to\s+lowest|'
        r'largest\s+to\s+smallest|greatest\s+to\s+least)\b',
        question, re.I,
    ):
        order['direction'] = 'DESC'
    elif re.search(
        r'\b(?:asc|ascending|lowest\s+to\s+highest|'
        r'smallest\s+to\s+largest|least\s+to\s+greatest)\b',
        question, re.I,
    ):
        order['direction'] = 'ASC'
    return answer

def _derive_unique_mapping_endpoints(answer, graph, registry, exact_shapes):
    """Fill omitted endpoints only when each selected mapping has one named pair."""
    if answer.get('status') != 'selected' or answer.get('identifier_path_ids') != []:
        return answer
    mids = answer.get('mapping_ids')
    if not isinstance(mids, list) or not mids or not all(isinstance(m, str) for m in mids):
        return answer
    edges = {e['id']: e for e in graph['mapping_candidates']}
    paths = {p['id']: p for p in graph['identifier_path_candidates']}
    selected = []
    for mid in mids:
        edge = edges.get(mid)
        if edge is None:
            return answer
        pairs = []
        for pair in edge.get('join_alternatives', []):
            ids = (pair['left_id'], pair['right_id'])
            if all(pid in paths and paths[pid]['owner_shape_uri'] in
                   exact_shapes.get(paths[pid]['domain'], set()) for pid in ids):
                pairs.append(ids)
        if len(set(pairs)) != 1:
            return answer
        selected.extend(pairs[0])
    selected = list(dict.fromkeys(selected))
    try:
        validate_mapping_graph_selection(mids, selected, graph, registry)
    except Exception:
        return answer
    return {**answer, 'identifier_path_ids': selected}


def _normalize_mapping_owner_participation(answer, candidates, graph, registry,
                                           exact_shapes, question):
    """Add explicitly named, approved join owners as existence participants.

    This does not infer projections, and does not repair invalid mappings.
    """
    if answer.get('status') != 'selected':
        return answer
    mids = answer.get('mapping_ids')
    pids = answer.get('identifier_path_ids')
    if not isinstance(mids, list) or not isinstance(pids, list):
        return answer
    try:
        selected = validate_mapping_graph_selection(mids, pids, graph, registry)
    except Exception:
        return answer
    if not selected:
        return answer
    lookup = {c['id']: c for c in candidates}
    participants = set(answer.get('projection_ids') or []) | set(
        answer.get('existence_ids') or [])
    if answer.get('count_target_id'):
        participants.add(answer['count_target_id'])
    existence = answer.get('existence_ids')
    if not isinstance(existence, list):
        return answer
    endpoints = {p['id']: p for p in graph['identifier_path_candidates']}
    for pid in pids:
        endpoint = endpoints.get(pid)
        if endpoint is None:
            continue
        domain, owner_uri = endpoint['domain'], endpoint['owner_shape_uri']
        if owner_uri not in exact_shapes.get(domain, set()):
            continue
        owner_candidates = [
            c for c in candidates
            if c.get('kind') == 'result' and c.get('domain') == domain
            and (c.get('node_uris') or [None])[-1] == owner_uri
        ]
        if len(owner_candidates) != 1:
            continue
        owner = owner_candidates[0]
        label = owner.get('path', '').split(' → ')[-1].strip()
        if not label or not re.search(
            r'(?<!\w)' + re.escape(label) + r's?(?!\w)', question, re.I
        ):
            continue
        already_present = any(
            lookup.get(cid, {}).get('kind') == 'result'
            and lookup[cid].get('domain') == domain
            and (lookup[cid].get('node_uris') or [None])[-1] == owner_uri
            for cid in participants
        )
        if not already_present:
            existence.append(owner['id'])
            participants.add(owner['id'])
    return answer


def _cross_validate(answer, candidates, graph, registry, domains, question,
                    exact_shapes, exact_properties):
    errors = []
    if not isinstance(answer, dict):
        return ['Response must be a JSON object'], []
    extra = {'mapping_ids', 'identifier_path_ids'}
    expected = {'status', 'projection_ids', 'existence_ids', 'filters',
                'boolean_operator', 'join', 'count_target_id', 'order_by',
                'limit', 'join_owner_id', 'reason'} | extra
    if set(answer) != expected:
        errors.append('Missing cross-domain plan fields')
    base = {k: v for k, v in answer.items() if k not in extra}
    errors.extend(validate_output(base, candidates))
    mids = answer.get('mapping_ids')
    pids = answer.get('identifier_path_ids')
    if not isinstance(mids, list) or not isinstance(pids, list):
        errors.append('Mapping IDs and identifier path IDs must be arrays')
        return errors, []
    selected = []
    if answer.get('status') == 'selected':
        if not mids or not pids:
            errors.append('Cross-domain plan needs a verified mapping and endpoints')
        else:
            try:
                selected = validate_mapping_graph_selection(mids, pids, graph, registry)
            except Exception as exc:
                errors.append(f'Invalid cross-domain mapping selection: {exc}')
        linked = {d for m in selected for d in (m['left_domain'], m['right_domain'])}
        if linked != set(domains):
            errors.append('Selected mapping graph does not cover all requested domains')
        lookup = {c['id']: c for c in candidates}
        operation_ids = (
            list(answer.get('projection_ids') or []) +
            list(answer.get('existence_ids') or []) +
            [f.get('property_id') for f in answer.get('filters', []) if isinstance(f, dict)] +
            [o.get('property_id') for o in answer.get('order_by', []) if isinstance(o, dict)]
        )
        if answer.get('count_target_id'):
            operation_ids.append(answer['count_target_id'])
        # Each named shape must appear in an operation's SHACL ancestry;
        # mapping endpoints alone do not count as requested projections.
        for domain in domains:
            covered = set()
            for cid in operation_ids:
                c = lookup.get(cid, {})
                if c.get('domain') == domain:
                    covered.update(c.get('node_uris') or [])
            missing = exact_shapes[domain] - covered
            if missing:
                errors.append(f'Explicit {domain} concepts missing from selected operations: {sorted(missing)}')
        # Output coverage is distinct from participation in WHERE/ORDER BY.
        # For SELECT requests that coordinate named entities in the result
        # phrase, filters and mapping endpoints cannot stand in for projections.
        if answer.get('count_target_id') is None:
            result_phrase = re.split(
                r'\b(?:where|ordered|ordering|sort|sorting|limit|limited)\b',
                question, maxsplit=1, flags=re.I,
            )[0]
            if re.search(r'\b(?:show|retrieve|return|list|display)\b', result_phrase, re.I):
                mentions = []
                for domain in domains:
                    for c in candidates:
                        if c.get('domain') != domain or c.get('kind') != 'result':
                            continue
                        label = c.get('path', '').split(' → ')[-1].strip()
                        if label and re.search(
                            r'(?<!\w)' + re.escape(label) + r's?(?!\w)',
                            result_phrase, re.I,
                        ):
                            mentions.append((domain, label))
                            break
                if len({d for d, _ in mentions}) > 1 and re.search(
                    r'\b(?:and|paired\s+with|together\s+with)\b',
                    result_phrase, re.I,
                ):
                    projected = set()
                    for cid in answer.get('projection_ids') or []:
                        c = lookup.get(cid, {})
                        projected.update((c.get('domain'), uri)
                                         for uri in c.get('node_uris') or [])
                    for domain, _ in mentions:
                        missing_output = exact_shapes[domain] - {
                            uri for d, uri in projected if d == domain
                        }
                        if missing_output:
                            errors.append(
                                f'Explicit {domain} result concepts missing from projections: '
                                f'{sorted(missing_output)}'
                            )
        for f in answer.get('filters', []):
            if not isinstance(f, dict):
                continue
            c = lookup.get(f.get('property_id'), {})
            domain = c.get('domain')
            if domain and (c.get('property_name') or '').casefold() not in exact_properties[domain]:
                errors.append(f'Filter {f.get("property_id")} lacks exact property-name evidence')
        comparisons = _explicit_shacl_comparisons(question, candidates)
        expected_comparisons = {
            (name, op, value.casefold()) for name, op, value in comparisons
        }
        actual_comparisons = set()
        for f in answer.get('filters', []):
            if not isinstance(f, dict):
                continue
            c = lookup.get(f.get('property_id'), {})
            value = f.get('value')
            if not isinstance(value, str):
                continue
            triple = ((c.get('property_name') or '').casefold(),
                      f.get('operator'), value.casefold())
            actual_comparisons.add(triple)
            if triple not in expected_comparisons:
                errors.append(f'Unrequested or mismatched WHERE comparison: {triple}')
        for triple in sorted(expected_comparisons - actual_comparisons):
            errors.append(f'Missing explicit WHERE comparison: {triple}')
        # An identifier's direct SHACL owner must be an explicitly named
        # entity and participate as a selected result/existence/count entity.
        # Domain roots are context, not joinable entity owners.
        result_ids = (list(answer.get('projection_ids') or []) +
                      list(answer.get('existence_ids') or []))
        if answer.get('count_target_id'):
            result_ids.append(answer['count_target_id'])
        selected_owners = {
            (lookup[cid]['domain'], lookup[cid]['node_uris'][-1])
            for cid in result_ids if cid in lookup
            and lookup[cid].get('kind') == 'result'
            and lookup[cid].get('node_uris')
        }
        offered_identifiers = {
            p['id']: p for p in graph['identifier_path_candidates']
        }
        for pid in pids:
            endpoint = offered_identifiers.get(pid)
            if endpoint is None:
                continue  # Existing mapping graph validation reports this.
            domain = endpoint['domain']
            owner = endpoint['owner_shape_uri']
            if owner not in exact_shapes[domain]:
                errors.append(f'Identifier {pid} owner is not an explicitly named concept')
            if (domain, owner) not in selected_owners:
                errors.append(f'Identifier {pid} owner is not a selected entity')
        requested_limit = _explicit_limit(question)
        if answer.get('limit') != requested_limit:
            errors.append('LIMIT disagrees with question')
        if bool(answer.get('count_target_id')) != bool(re.search(
                r'\b(count|how many|number of)\b', question, re.I)):
            errors.append('COUNT disagrees with question')
        if bool(answer.get('order_by')) != bool(_explicit_sort(question)):
            errors.append('ORDER BY disagrees with question')
        if answer.get('order_by'):
            direction = 'DESC' if re.search(
                r'\b(?:desc|descending|highest\s+to\s+lowest|'
                r'largest\s+to\s+smallest|greatest\s+to\s+least)\b',
                question, re.I) else 'ASC'
            if any(o.get('direction') != direction for o in answer['order_by']):
                errors.append('ORDER BY direction disagrees with question')
    elif mids or pids:
        errors.append('Nonselected plan must not select mapping paths')
    return errors, selected


def run_cross_domain(indices, question, *, mapping_file, method='expanded',
                     dry_run=False, model='qwen2.5-coder:7b',
                     endpoint='http://127.0.0.1:11434',
                     embedding_model='nomic-embed-text:latest',
                     top_shapes=8, top_properties=8,
                     max_candidates=128, max_depth=6):
    domains = tuple(sorted(indices))
    record = {'question': question, 'domains': list(domains),
              'retrieval_method': method, 'model': model, 'qwen_calls': 0}
    unsupported_operations = _unsupported_intent(question)
    if unsupported_operations and not dry_run:
        return {**record, 'status': 'unsupported_phase2',
                'unsupported_operations': unsupported_operations,
                'reason': 'Unsupported Phase-2 operation; no Qwen call'}
    exact_shapes, exact_properties = {}, {}
    qualified_domains, candidates, evidence = {}, [], {}
    for domain in domains:
        index = indices[domain]
        shapes, props = _schema_anchors(index, question)
        if not shapes:
            return {**record, 'status': 'no_explicit_concept',
                    'reason': f'No explicitly named SHACL concept in {domain}; no Qwen call'}
        exact_shapes[domain] = set(shapes)
        exact_properties[domain] = {p['name'].casefold() for p in props.values()}
        # Check filter names against all domains after collecting all anchors.
        qualified, ev = build_candidates(index, question, method=method,
            endpoint=endpoint, embedding_model=embedding_model,
            top_shapes=top_shapes, top_properties=top_properties,
            max_candidates=max_candidates, max_depth=max_depth)
        qualified_domains[domain] = qualified
        evidence[domain] = ev
        candidates.extend(_scoped_candidates(domain, qualified))
    known_properties = set().union(*exact_properties.values())
    missing = [p for p in _explicit_filter_property_names(question)
               if p.casefold() not in known_properties]
    if missing:
        return {**record, 'status': 'ambiguous_property',
                'reason': 'Unrecognized exact filter properties: ' + ', '.join(missing)}
    registry = load_cross_domain_mappings(mapping_file)
    graph = qualify_mapping_graph(registry, qualified_domains)
    graph['mapping_candidates'] = [
        m for m in graph['mapping_candidates']
        if m['left_domain'] in domains and m['right_domain'] in domains
        and m['join_alternatives']
    ]
    allowed = {p for m in graph['mapping_candidates']
               for side in ('left', 'right')
               for p in m[f'{side}_identifier_candidate_ids']}
    graph['identifier_path_candidates'] = [
        p for p in graph['identifier_path_candidates'] if p['id'] in allowed]
    # Reuse the existing conservative N-domain owner/identifier narrowing.
    # Keep the full qualified graph and candidate registry for validation.
    original_candidates, original_graph = candidates, graph
    _, graph = _prune_explicit_candidates(question, candidates, graph)
    # Restrict offered mapping alternatives to directly owned, explicitly
    # named SHACL entities. A domain root is context, not an entity owner.
    # When a domain has no unambiguous non-root anchor, retain its alternatives.
    explicit_owners = {}
    for domain in domains:
        named = {
            c['node_uris'][-1] for c in candidates
            if c['domain'] == domain and c['kind'] == 'result'
            and len(c.get('node_uris') or []) > 1
            and c['node_uris'][-1] in exact_shapes[domain]
        }
        if named:
            explicit_owners[domain] = named
    retained_paths = [
        p for p in graph['identifier_path_candidates']
        if p['domain'] not in explicit_owners
        or p['owner_shape_uri'] in explicit_owners[p['domain']]
    ]
    retained_ids = {p['id'] for p in retained_paths}
    narrowed_mappings = []
    for mapping in graph['mapping_candidates']:
        left = [pid for pid in mapping['left_identifier_candidate_ids']
                if pid in retained_ids]
        right = [pid for pid in mapping['right_identifier_candidate_ids']
                 if pid in retained_ids]
        alternatives = [
            pair for pair in mapping['join_alternatives']
            if pair['left_id'] in left and pair['right_id'] in right
        ]
        if not alternatives:
            continue
        approved_pairs = mapping.get('approved_owner_pair_candidate_ids')
        narrowed_mappings.append({
            **mapping,
            'left_identifier_candidate_ids': left,
            'right_identifier_candidate_ids': right,
            'join_alternatives': alternatives,
            'approved_owner_pair_candidate_ids': (
                [pair for pair in approved_pairs
                 if pair['left_id'] in left and pair['right_id'] in right]
                if approved_pairs is not None else None
            ),
        })
    used_ids = {
        pid for mapping in narrowed_mappings
        for side in ('left', 'right')
        for pid in mapping[f'{side}_identifier_candidate_ids']
    }
    graph = {
        'mapping_candidates': narrowed_mappings,
        'identifier_path_candidates': [
            p for p in retained_paths if p['id'] in used_ids
        ],
    }
    identifier_ids = {p['id'] for p in graph['identifier_path_candidates']}
    # URI ancestry alone admits unrelated descendants and domain roots.
    # Match complete displayed SHACL labels, never substrings or synonyms.
    def explicitly_named(label):
        return bool(re.search(r'(?<!\\w)' + re.escape(label) + r'(?!\\w)',
                              question, flags=re.IGNORECASE))

    named_owners = {
        d: {
            c['path'].split(' → ')[-1].strip().casefold()
            for c in candidates
            if c['domain'] == d and c['kind'] == 'result'
            and len(c['path'].split(' → ')) > 1
            and explicitly_named(c['path'].split(' → ')[-1].strip())
        }
        for d in domains
    }
    prompt_candidates = []
    for c in candidates:
        parts = [part.strip() for part in c['path'].split(' → ')]
        domain = c['domain']
        if c['kind'] == 'result':
            if len(parts) > 1 and parts[-1].casefold() in named_owners[domain]:
                prompt_candidates.append(c)
        elif c['kind'] == 'property':
            if c['id'] in identifier_ids or (
                len(parts) > 2
                and parts[-2].casefold() in named_owners[domain]
                and (c.get('property_name') or parts[-1]).casefold()
                    in exact_properties[domain]
            ):
                prompt_candidates.append(c)
    # No evidence-based narrowing is possible: preserve the original choices.
    if not prompt_candidates:
        prompt_candidates, graph = original_candidates, original_graph
    # Apply after all fallback paths so explicit intent cannot be restored away.
    graph = restrict_shared_key(question, graph)
    record['explicit_shared_key'] = explicit_shared_key(question)
    record.update(candidate_paths=candidates, candidate_count=len(candidates),
                  result_candidate_count=sum(c['kind'] == 'result' for c in candidates),
                  property_candidate_count=sum(c['kind'] == 'property' for c in candidates),
                  mapping_candidates=graph['mapping_candidates'],
                  identifier_path_candidates=graph['identifier_path_candidates'],
                  retrieval_evidence=evidence, system_prompt=CROSS_DOMAIN_PROMPT)
    if not graph['mapping_candidates']:
        return {**record, 'status': 'no_approved_cross_domain_mapping',
                'reason': 'No approved SHACL-qualified mapping; no Qwen call'}
    if not candidates:
        return {**record, 'status': 'no_candidates'}
    # Reuse the existing compact N-domain representation; preserve Phase-1
    # result/property candidates and mapping choices without validator metadata.
    compact = compact_n_domain_prompt({
        'question': question,
        'result_candidates': prompt_candidates,
        'identifier_path_candidates': graph['identifier_path_candidates'],
        'mapping_candidates': graph['mapping_candidates'],
    })
    # Expose verified identifier ownership next to each result candidate.
    # This is presentation only: Qwen still chooses COUNT/existence roles,
    # and the original graph/registry remain authoritative for validation.
    owner_identifiers = {}
    for identifier in compact['identifiers']:
        owner_identifiers.setdefault(
            (identifier['domain'], identifier['owner'].casefold()), []
        ).append(identifier['id'])
    result_choices = []
    for candidate in compact['results']:
        choice = dict(candidate)
        if choice['kind'] == 'result':
            owner = choice['path'].split(' → ')[-1].strip().casefold()
            choice['identifier_path_ids'] = owner_identifiers.get(
                (choice['domain'], owner), [])
        result_choices.append(choice)
    prompt = {'question': question, 'domains': list(domains),
              'candidates': result_choices,
              'mapping_candidates': compact['mappings'],
              'identifier_path_candidates': compact['identifiers']}
    record['prompt_candidate_count'] = len(prompt_candidates)
    record['prompt_join_alternatives'] = sum(
        len(m['allowed_pairs']) for m in compact['mappings'])
    record['prompt_characters'] = len(json.dumps(prompt, ensure_ascii=False))
    record['user_prompt'] = prompt
    if dry_run:
        return {**record, 'status': 'dry_run'}
    try:
        started = time.perf_counter()
        record['qwen_calls'] = 1
        raw = ollama_select(prompt, model=model, endpoint=endpoint,
                            system_prompt=CROSS_DOMAIN_PROMPT)
        record['elapsed_seconds'] = round(time.perf_counter() - started, 3)
        record['raw_response'] = raw
        selection = json.loads(raw)
        record['raw_selection'] = selection
        answer = _construct_cross_domain_plan(selection, graph, registry, exact_shapes)
        # Shared Phase-1 projection normalization handles property-only returns.
        base = {k: v for k, v in answer.items()
                if k not in ('mapping_ids', 'identifier_path_ids')}
        base = normalize_property_only_projections(base, candidates, question)
        answer = {**base, 'mapping_ids': answer.get('mapping_ids'),
                  'identifier_path_ids': answer.get('identifier_path_ids')}
        # Cross-domain join ownership is represented by approved mapping
        # endpoints, never by the single-domain join_owner_id field.
        if answer.get('status') == 'selected':
            answer['join_owner_id'] = None
        answer = _normalize_explicit_sort_and_placeholder_filters(
            answer, candidates, question)
        answer = _derive_unique_mapping_endpoints(answer, graph, registry, exact_shapes)
        answer = _normalize_mapping_owner_participation(
            answer, candidates, graph, registry, exact_shapes, question)
        errors, selected = _cross_validate(
            answer, candidates, graph, registry, domains, question,
            exact_shapes, exact_properties)
        if answer.get('status') == 'selected':
            answer['join'] = bool(selected)
        record.update(answer=answer, validation_errors=errors,
                      validated_mappings=selected,
                      status='valid_response' if not errors else 'invalid_response')
    except json.JSONDecodeError as exc:
        record.update(status='invalid_json', validation_errors=[str(exc)])
    except Exception as exc:
        record.update(status='error', error=f'{type(exc).__name__}: {exc}')
    return record
