"""Opt-in experimental semantic path pipeline; never used by default planner."""
from .evidence_path_binding import bind_evidenced_path
from .evidence_path_selection import select_evidenced_path
from .unified_answer import enumerate_evidenced_paths


def plan_evidenced_path(question, catalog, mappings, start, end, *,
                       projections, filter_spec=None, enabled=False,
                       model="llama3.1:8b", request_json=None,
                       ollama_host="http://localhost:11434", timeout=120,
                       keep_alive=None):
    """Select a path with an LLM and bind it only when all evidence is verified.

    The caller explicitly supplies grounded output/filter requirements; this
    function never infers or silently drops them. Not wired into generate_ir.
    Returns (IR or None, diagnostics). None means abstention/no valid path.
    """
    if not enabled:
        return None, {"status": "disabled"}
    if not callable(request_json):
        raise TypeError("request_json must be callable when enabled")
    if not isinstance(projections, list) or not projections:
        raise ValueError("Explicit grounded projections required")
    paths = enumerate_evidenced_paths(
        catalog, mappings, start, end, max_hops=4, max_paths=32)
    if not paths:
        return None, {"status": "no_evidenced_paths"}
    selected, diagnostics = select_evidenced_path(
        question, paths, model=model, request_json=request_json,
        ollama_host=ollama_host, timeout=timeout, keep_alive=keep_alive)
    if selected is None:
        return None, diagnostics
    # Fail closed: binding rechecks path evidence, property ownership, and
    # every caller-supplied projection/filter. Never fall back to an invented IR.
    plan = bind_evidenced_path(
        selected, catalog, mappings, projections=projections,
        filter_spec=filter_spec)
    return plan, diagnostics
