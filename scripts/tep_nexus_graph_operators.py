"""Constrained, deterministic operators over an already retrieved virtual graph.

These operations do not execute arbitrary SPARQL/SQL and cannot retrieve data
outside the bounded live query result.
"""
from __future__ import annotations


def resolve_function(graph, function_id):
    matches = [n for n in graph["nodes"] if n["type"] == "EngineeringFunction"
               and n["localId"] == function_id]
    if len(matches) != 1:
        raise ValueError("Engineering function missing or ambiguous")
    node = matches[0]
    relations = [e for e in graph["edges"] if e["source"] == node["id"]]
    return {"function": node, "relationships": relations}


def get_observations(graph, *, start_seconds=None, end_seconds=None):
    if start_seconds is not None and (not isinstance(start_seconds, (int, float)) or isinstance(start_seconds, bool)):
        raise ValueError("Invalid lower time bound")
    if end_seconds is not None and (not isinstance(end_seconds, (int, float)) or isinstance(end_seconds, bool)):
        raise ValueError("Invalid upper time bound")
    import math
    if any(not math.isfinite(v) for v in (start_seconds, end_seconds) if v is not None):
        raise ValueError("Non-finite time bound")
    if start_seconds is not None and end_seconds is not None and start_seconds > end_seconds:
        raise ValueError("Reversed time bounds")
    return [n for n in graph["nodes"] if n["type"] == "VirtualObservation"
            and (start_seconds is None or n["simulationTimeHours"] * 3600 >= start_seconds)
            and (end_seconds is None or n["simulationTimeHours"] * 3600 <= end_seconds)]


def traverse_relationships(graph, resource_id, *, predicate=None):
    if resource_id not in {n["id"] for n in graph["nodes"]}:
        raise ValueError("Unknown virtual graph resource")
    return [e for e in graph["edges"] if e["source"] == resource_id
            and (predicate is None or e["predicate"] == predicate)]
