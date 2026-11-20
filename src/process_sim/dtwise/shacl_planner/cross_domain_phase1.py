"""Standalone cross-domain Phase-1 planning: one Qwen call, approved joins only.

Reuses single-domain candidate retrieval, operation contract, and mapping graph.
No SPARQL generation or execution.
"""
from __future__ import annotations

import json
import re
import time

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
)

CROSS_DOMAIN_PROMPT = SYSTEM_PROMPT.replace(
    'Return EXACTLY these keys, using null/[] for unused fields:',
    'Return the Phase-1 keys plus mapping_ids and identifier_path_ids. '
    'All candidate IDs are domain-qualified (e.g. ecad:R2). '
    'Select only offered mapping IDs and offered identifier paths. '
    'For every selected mapping select its exact owner-specific identifier endpoints. '
    'Cross-domain joins use approved identifier equality; never invent RDF edges. '
    'Prefer an approved AssetIdentifier mapping when available and compatible. '
    'If no connected approved mapping exists, return unresolved with empty plan. '
    'COUNT targets a result entity, not raw joined rows. '
    'Return EXACTLY these keys, using null/[] for unused fields:'
).replace(
    '"reason":"brief explanation"\n}',
    '"reason":"brief explanation",\n "mapping_ids":["approved-mapping-id"],\n '
    '"identifier_path_ids":["ecad:P1","dexpi:P2"]\n}'
) + """
For selected plans, include every explicitly requested WHERE comparison in filters.
Use only the offered property candidate whose exact SHACL property label is
named in the question. Copy the literal value from the question verbatim and
use the comparison operator requested (use "=" for "is" or "equals").
A valid cross-domain mapping does not replace or satisfy a WHERE filter.
Before returning selected, check that no explicitly requested filter was omitted.
If a requested filter cannot be represented by offered candidates, return
unresolved instead of silently dropping it.
For ambiguous/unresolved/unsupported, mapping_ids and identifier_path_ids MUST be [].
Do not use any additional model calls. Python verifies all selections.
"""


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
        for f in answer.get('filters', []):
            if not isinstance(f, dict):
                continue
            c = lookup.get(f.get('property_id'), {})
            domain = c.get('domain')
            if domain and (c.get('property_name') or '').casefold() not in exact_properties[domain]:
                errors.append(f'Filter {f.get("property_id")} lacks exact property-name evidence')
        literals = _constraint_literals(question)
        values = {f.get('value', '').casefold() for f in answer.get('filters', [])
                  if isinstance(f, dict) and isinstance(f.get('value'), str)}
        for literal in literals:
            if literal.casefold() not in values:
                errors.append(f'Missing explicit filter value: {literal}')
        requested_limit = _explicit_limit(question)
        if answer.get('limit') != requested_limit:
            errors.append('LIMIT disagrees with question')
        if bool(answer.get('count_target_id')) != bool(re.search(
                r'\b(count|how many|number of)\b', question, re.I)):
            errors.append('COUNT disagrees with question')
        if bool(answer.get('order_by')) != bool(_explicit_sort(question)):
            errors.append('ORDER BY disagrees with question')
        if answer.get('order_by'):
            direction = 'DESC' if re.search(r'\b(desc|descending)\b', question, re.I) else 'ASC'
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
    if _unsupported_intent(question) and not dry_run:
        return {**record, 'status': 'unsupported_phase2',
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
    prompt = {'question': question, 'domains': list(domains),
              'candidates': compact['results'],
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
        answer = json.loads(raw)
        # Shared Phase-1 projection normalization handles property-only returns.
        base = {k: v for k, v in answer.items()
                if k not in ('mapping_ids', 'identifier_path_ids')}
        base = normalize_property_only_projections(base, candidates, question)
        answer = {**base, 'mapping_ids': answer.get('mapping_ids'),
                  'identifier_path_ids': answer.get('identifier_path_ids')}
        errors, selected = _cross_validate(
            answer, candidates, graph, registry, domains, question,
            exact_shapes, exact_properties)
        if answer.get('status') == 'selected':
            answer['join'] = bool(selected)
            answer['join_owner_id'] = None
        record.update(answer=answer, validation_errors=errors,
                      validated_mappings=selected,
                      status='valid_response' if not errors else 'invalid_response')
    except json.JSONDecodeError as exc:
        record.update(status='invalid_json', validation_errors=[str(exc)])
    except Exception as exc:
        record.update(status='error', error=f'{type(exc).__name__}: {exc}')
    return record
