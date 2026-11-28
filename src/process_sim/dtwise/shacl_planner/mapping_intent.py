"""Conservative explicit shared-key contract for cross-domain requests."""
import re

def explicit_shared_key(question):
    # Only the supported single-token shared-key syntax; not general NL parsing.
    hits = re.findall(r'\bjoin(?:ed|ing)?\s+(?:by|using|on)\s+([A-Za-z][A-Za-z0-9_]*)\b', question, re.I)
    return hits[0].casefold() if len(hits) == 1 else None

def compatible_mapping_ids(question, graph):
    key = explicit_shared_key(question)
    if key is None:
        return None
    paths = {p['id']: p for p in graph['identifier_path_candidates']}
    def matches(pid):
        return paths.get(pid, {}).get('path', '').split(' → ')[-1].strip().casefold() == key
    return {m['id'] for m in graph['mapping_candidates']
            if any(matches(p['left_id']) and matches(p['right_id'])
                   for p in m['join_alternatives'])}

def restrict_shared_key(question, graph):
    allowed = compatible_mapping_ids(question, graph)
    if allowed is None:
        return graph
    key = explicit_shared_key(question)
    ids = {p['id'] for p in graph['identifier_path_candidates']
           if p['path'].split(' → ')[-1].strip().casefold() == key}
    edges = []
    for m in graph['mapping_candidates']:
        if m['id'] not in allowed:
            continue
        pairs = [p for p in m['join_alternatives'] if p['left_id'] in ids and p['right_id'] in ids]
        left = {p['left_id'] for p in pairs}
        right = {p['right_id'] for p in pairs}
        approved = m.get('approved_owner_pair_candidate_ids')
        edges.append({**m, 'join_alternatives':pairs,
                      'left_identifier_candidate_ids':sorted(left),
                      'right_identifier_candidate_ids':sorted(right),
                      'approved_owner_pair_candidate_ids':None if approved is None else
                      [p for p in approved if p['left_id'] in left and p['right_id'] in right]})
    used = {pid for m in edges for side in ('left','right') for pid in m[f'{side}_identifier_candidate_ids']}
    return {**graph,'mapping_candidates':edges,
            'identifier_path_candidates':[p for p in graph['identifier_path_candidates'] if p['id'] in used]}
