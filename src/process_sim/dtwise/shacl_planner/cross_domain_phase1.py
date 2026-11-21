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
    'For COUNT, use the same single-domain contract: count_target_id identifies the entity whose instances the user wants counted. Other entities needed only to establish cross-domain matches belong in existence_ids. Interpret semantic roles from the whole question, not word position or mapping direction. Do not count the matching/existence entity or raw joined rows unless that is explicitly what the user asks to count. '
    'Return EXACTLY these keys, using null/[] for unused fields:'
).replace(
    '"reason":"brief explanation"\n}',
    '"reason":"brief explanation",\n "mapping_ids":["approved-mapping-id"],\n '
    '"identifier_path_ids":["ecad:P1","dexpi:P2"]\n}'
) + """
For SELECT queries, include every entity the user requests as an output in projection_ids, including paired or corresponding entities. Use existence_ids only for entities needed to establish matching but not requested as outputs. Mapping endpoints never replace requested projections.
Cross-domain identifier matching is represented ONLY by mapping_ids and
identifier_path_ids. It is NOT a literal WHERE filter. For a question that
requests matching entities by a shared identifier but specifies no literal
comparison, filters MUST be [] and boolean_operator MUST be "NONE".
Never invent, infer, or insert placeholder values such as <question literal>,
<identifier value>, or values copied from another entity. A filter is permitted
only when the question explicitly supplies a literal comparison value.
Each selected identifier endpoint must be directly owned by an entity explicitly
requested in the question and included in projection_ids, existence_ids, or
count_target_id. Do not add endpoints from unrelated entities merely because
they share a property predicate or are offered as mapping alternatives.
For selected plans, include every explicitly requested WHERE comparison in filters.
boolean_operator combines WHERE filters only, not the cross-domain JOIN.
Use AND when the question combines multiple filter conditions with AND,
OR when it combines them with OR, and NONE only for zero or one filter.
Do not return NONE when two or more filters are selected.
Use only the offered property candidate whose exact SHACL property label is
named in the question. Copy the literal value from the question verbatim and
use the comparison operator requested (use "=" for "is" or "equals").
A valid cross-domain mapping does not replace or satisfy a WHERE filter.
For cross-domain COUNT, count_target_id identifies the result entity being counted.
Put other explicitly requested result entities required to establish the matching
condition in existence_ids, even when their identifiers are mapping endpoints.
Mapping endpoints do not replace existence requirements. Do not duplicate the
COUNT target in existence_ids.
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



def _explicit_shacl_comparisons(question, candidates):
    """Find explicit property comparisons using offered SHACL labels, not IDs."""
    names = sorted({
        c.get('property_name') for c in candidates
        if c.get('kind') == 'property' and c.get('property_name')
    }, key=len, reverse=True)
    comparisons = []
    for name in names:
        pattern = (
            r'(?<!\w)' + re.escape(name) + r'(?!\w)'
            r'\s+(?:(?P<op>is|equals|equal\s+to|!=|>=|<=|=|>|<|to)\s+)?'
            r'(?P<value>[A-Za-z0-9_][\w.-]*)'
        )
        for match in re.finditer(pattern, question, re.I):
            operator = (match.group('op') or '').casefold()
            value = match.group('value').rstrip('.,;?!')
            prefix = question[:match.start()]
            if operator == 'to' and value.casefold() in {
                'connect', 'join', 'match', 'link', 'associate', 'relate',
                'connects', 'joins', 'matches', 'links', 'associates', 'relates',
            }:
                # Infinitive join language is not a literal comparison.
                continue
            if not operator and not re.search(
                r'\b(?:with|where|whose|having|restrict(?:ed|ing)?|'
                r'filter(?:ed|ing)?|of\s+type|of)\b[^.;?!]*$',
                prefix, re.I,
            ):
                continue
            # Sorting phrases name a property but do not compare it to a value.
            if not operator and value.casefold() in {
                'asc', 'desc', 'ascending', 'descending', 'from',
                'in', 'sorted', 'ordered', 'lowest', 'highest',
            }:
                continue
            if value.casefold() in {
                'and', 'or', 'by', 'where', 'with', 'through', 'using',
                'whose', 'is', 'equals', 'equal', 'the', 'a', 'an',
            }:
                continue
            comparisons.append((
                name.casefold(),
                operator if operator in {'!=', '>', '<', '>=', '<=', '='} else '=',
                value,
            ))
    return comparisons



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



