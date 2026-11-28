"""Remove explicit ownership presentation only; never mutate validator inputs."""
from copy import deepcopy

def ablate_prompt(prompt):
    result=deepcopy(prompt)
    for c in result.get('candidates',[]):
        if 'path' in c:
            c['path']=c['path'].split('→')[-1].strip()
        c.pop('identifier_path_ids',None)
    for c in result.get('identifier_path_candidates',[]):
        c.pop('owner',None)
    return result
