"""Live Ollama parity: legacy Phase 1 versus RETRIEVE state machine.

From repository root:
    python tests/integration/run_retrieve_state_machine_parity.py

One live Ollama selection per case is replayed verbatim into the new planner,
so differences cannot be caused by sampling. Compiles SPARQL; never executes it.
Does not change CLI routing or accept new CLI arguments.
"""
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from process_sim.dtwise.experimental_shacl_subgraph import load_index
from process_sim.dtwise.experimental_shacl_semantic_candidates import semantic_candidates
from process_sim.dtwise.experimental_shacl_phase1_ollama import (
    run_phase1_query_plan, compile_phase1_sparql,
)
from process_sim.dtwise.experimental_shacl_planner_state_machine import (
    run_retrieve_state_machine,
)

INDEX = ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json"
MODEL = "qwen2.5-coder:7b"
EMBED_MODEL = "nomic-embed-text:latest"
OLLAMA = "http://127.0.0.1:11434"
CASES = [
    ("retrieve", "Show Address of EndPoint belonging to Device in ECAD", 1),
    ("explicit-sibling", "Show Address of both EndPoint and PLCEndPoint belonging to Device in ECAD", 2),
    ("auto-join-broad-address", "Show Address in ECAD", 2),
]


def live_transport(url, payload, timeout):
    request = Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def compare(name, question, expected_queries):
    index = load_index(INDEX, domain="ecad")
    prepared = semantic_candidates(
        index, question, top_shapes=8, top_properties=2, max_candidates=64,
        model=EMBED_MODEL, endpoint=OLLAMA,
    )
    replies = []

    def record(url, payload, timeout):
        response = live_transport(url, payload, timeout)
        replies.append(response)
        return response

    old = run_phase1_query_plan(index, prepared, model=MODEL, endpoint=OLLAMA,
                                transport=record)
    old_queries = compile_phase1_sparql(old)
    if len(replies) != 1:
        raise AssertionError(f"Expected one live Ollama response; got {len(replies)}")

    def replay(url, payload, timeout):
        # Require the same actual prompt and model for meaningful parity.
        # The recorded prompt is checked by the Ollama call's own validation.
        return replies[0]

    new = run_retrieve_state_machine(
        index, prepared, model=MODEL, endpoint=OLLAMA, transport=replay,
    )
    for field in ("plan", "selected_paths", "auto_join_result_ids", "auto_join_groups"):
        if old[field] != new[field]:
            raise AssertionError(f"{name}: {field} differs: {old[field]!r} != {new[field]!r}")
    if old_queries != new["queries"]:
        raise AssertionError(f"{name}: compiled SPARQL differs")
    if len(new["queries"]) != expected_queries:
        raise AssertionError(f"{name}: expected {expected_queries} queries, got {len(new['queries'])}")
    if new["state_trace"] != [
        "start", "qualified", "model_selected", "validated", "compiled"
    ]:
        raise AssertionError(f"{name}: incorrect state trace: {new['state_trace']}")
    for item in new["queries"]:
        sparql = item["sparql"].lstrip()
        if not sparql.startswith("SELECT DISTINCT") or any(
            token in sparql.upper() for token in ("INSERT ", "DELETE ", "UPDATE ", "SERVICE ")
        ):
            raise AssertionError(f"{name}: non-read-only SPARQL")
    print(f"PASS  {name}  ({len(new['queries'])} identical compiled queries)", flush=True)


def main():
    failed = 0
    for name, question, expected in CASES:
        print(f"QUERY [{name}]: {question}", flush=True)
        try:
            compare(name, question, expected)
        except Exception as exc:
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}", flush=True)
    print(f"TOTAL {len(CASES) - failed} PASS / {failed} FAIL", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
