"""Live parity for remaining single-domain operations; no SPARQL execution.

Run from repository root:
    python tests/integration/run_single_domain_state_machine_parity.py
"""
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from process_sim.dtwise.experimental_shacl_subgraph import load_index
from process_sim.dtwise.experimental_shacl_semantic_candidates import semantic_candidates
from process_sim.dtwise.experimental_shacl_planner_state_machine import run_single_domain_state_machine
from process_sim.dtwise.experimental_shacl_phase2_filter import run_phase2_filter_plan, compile_phase2_filter_sparql
from process_sim.dtwise.experimental_shacl_phase3_and import run_phase3_and_plan, compile_phase3_and_sparql
from process_sim.dtwise.experimental_shacl_phase4_join import run_phase4_join_plan, compile_phase4_join_sparql
from process_sim.dtwise.experimental_shacl_phase4_filtered_join import (
    run_phase4_filtered_join_plan, compile_phase4_filtered_join_sparql,
)
from tests.integration.run_shacl_planner import CASES, check

INDEX = ROOT / "semantic/ontology2/dtwise/dtwise-schema-index.json"
MODEL = "qwen2.5-coder:7b"
EMBED_MODEL = "nomic-embed-text:latest"
OLLAMA = "http://127.0.0.1:11434"
OPERATIONS = {
    "--phase2-filter": ("phase2-filter", run_phase2_filter_plan, compile_phase2_filter_sparql),
    "--phase3-and": ("phase3-and", run_phase3_and_plan, compile_phase3_and_sparql),
    "--phase4-join": ("phase4-join", run_phase4_join_plan, compile_phase4_join_sparql),
    "--phase4-filtered-join": ("phase4-filtered-join", run_phase4_filtered_join_plan,
                              compile_phase4_filtered_join_sparql),
}


def live_transport(url, payload, timeout):
    request = Request(url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def compare(test):
    operation, old_runner, old_compiler = OPERATIONS[test["mode"]]
    question = test["question"]
    index = load_index(INDEX, domain="ecad")
    wide = operation in ("phase2-filter", "phase4-join", "phase4-filtered-join")
    prepared = semantic_candidates(
        index, question, top_shapes=16 if wide else 8,
        top_properties=8, max_candidates=128 if wide else 64,
        model=EMBED_MODEL, endpoint=OLLAMA,
    )
    calls = []

    def record(url, payload, timeout):
        calls.append((url, payload))
        return live_transport(url, payload, timeout)

    # Capture the real response once; replay it into the new state machine.
    replies = []

    def capture(url, payload, timeout):
        response = record(url, payload, timeout)
        replies.append(response)
        return response

    old = old_runner(index, prepared, model=MODEL, endpoint=OLLAMA, transport=capture)
    old_sparql = old_compiler(old)
    if len(replies) != 1:
        raise AssertionError(f"Expected one real Qwen response, got {len(replies)}")

    def replay(url, payload, timeout):
        if (url, payload) != calls[0]:
            raise AssertionError("Ollama request differs")
        return replies[0]

    new = run_single_domain_state_machine(
        index, prepared, operation=operation, model=MODEL,
        endpoint=OLLAMA, transport=replay,
    )
    if old["plan"] != new["plan"]:
        raise AssertionError(f"Validated plan mismatch: {old['plan']} != {new['plan']}")
    compiled = new["queries"] if operation == "phase2-filter" else new["sparql"]
    if old_sparql != compiled:
        raise AssertionError("Compiled SPARQL differs")
    if new["state_trace"] != ["start", "qualified", "model_selected", "validated", "compiled"]:
        raise AssertionError(f"Unexpected trace: {new['state_trace']}")
    check(test, new)
    print(f"PASS  {test['name']}: identical plan and compiled SPARQL", flush=True)


def main():
    cases = [case for case in CASES if case["mode"] in OPERATIONS]
    failures = 0
    for case in cases:
        print(f"QUERY [{case['name']}]", flush=True)
        try:
            compare(case)
        except Exception as exc:
            failures += 1
            print(f"FAIL  {case['name']}: {type(exc).__name__}: {exc}", flush=True)
    print(f"TOTAL {len(cases)-failures} PASS / {failures} FAIL")
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
