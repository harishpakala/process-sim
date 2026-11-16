"""Experimental shared entry point for engineering and historian questions.

Both paths share intent routing and a normalized plan envelope. The engineering
SHACL planner and historian executor remain independent, validated backends.
"""
from __future__ import annotations

import re

from process_sim.api.historian_nl_experimental import plan_historian_question, canonical_historian_question
from process_sim.api.dtwise_query import run_question as run_engineering_question
from process_sim.api.vtkg_query import run_historian_question

_HISTORIAN = re.compile(
    r"\b(historian|history|historical|recorded|readings?|values?|measurements?|"
    r"observations?|samples?|trends?|plot|chart|graph|time.series|behav(?:e|ior|iour))\b", re.I
)
# These are hints, not sufficient to override a question with a different intent.
_HISTORIAN_STRONG = re.compile(
    r"\b(historian|history|historical|recorded|readings?|measurements?|"
    r"observations?|samples?|plot|chart|time.series)\b", re.I
)


def classify_intent(question: str) -> str:
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    if _HISTORIAN_STRONG.search(question):
        return "historian_observations"
    if _HISTORIAN.search(question) and re.search(r"\b(simulation|run|seconds?|FI[_-]\d+|LI[_-]\d+|PI[_-]\d+|TI[_-]\d+)\b", question, re.I):
        return "historian_observations"
    return "engineering_query"


def run_unified_experiment(question: str, *, context=None, environ=None) -> dict:
    """Dispatch by intent, never by client-supplied executor name."""
    intent = classify_intent(question)
    if intent == "engineering_query":
        result = run_engineering_question(question, environ=environ)
        return {"mode": "unified_nl_experimental", "intent": intent,
                "plan": result["plan"], "result": result}
    plan = plan_historian_question(question, context=context)
    payload = {key: plan[key] for key in ("domain", "engineering_function", "run_id",
               "start_simulation_seconds", "end_simulation_seconds")}
    payload["question"] = canonical_historian_question(plan)
    result = run_historian_question(payload, environ=environ)
    return {"mode": "unified_nl_experimental", "intent": intent,
            "plan": plan, "result": result}
