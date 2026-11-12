"""Focused VTKG function selection: hybrid retrieval -> Llama -> GraphDB mapping -> VTKG.

No keyword routing, no hardcoded TI_101 -> signal mapping, no aggregate computation.
The run-scoped registry is the source of supported engineering functions.
Run from repository root with TEP_TIMESCALE_DSN set for --execute.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def load(name, path):
    spec = spec_from_file_location(name, path)
    mod = module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--question", default="What is the average measured temperature of TI_101 over the last hour?")
    p.add_argument("--run-id", required=True, help="Actual simulation UUID, required for run-scoped mapping evidence")
    p.add_argument("--start-seconds", type=float, default=None)
    p.add_argument("--end-seconds", type=float, default=None)
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--vector-weight", type=float, default=0.75)
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--embedding-model", default="nomic-embed-text:latest")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", type=Path, default=Path("reports/vtkg_function_selection_diagnostic.json"))
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    if not 1 <= a.top_k <= 100 or not 0 <= a.vector_weight <= 1:
        p.error("Invalid top-k or vector-weight")
    if a.execute and (a.start_seconds is None or a.end_seconds is None):
        p.error("--execute requires explicit --start-seconds and --end-seconds; 'last hour' is not assumed")
    if a.execute and not os.environ.get("TEP_TIMESCALE_DSN"):
        p.error("--execute requires TEP_TIMESCALE_DSN")
    sys.path.insert(0, str(ROOT / "scripts"))
    from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
    from tep_nexus_live_virtual_graph import execute as execute_vtkg, validate_request
    retrieval = load("vtkg_exp30", HERE / "30_evaluate_simple_questions.py")
    llm = load("vtkg_exp33", HERE / "33_llm_sparql.py")
    registry = load_supported_functions(a.mapping_discovery, a.temporal_coverage, a.run_id)
    # Mapping names are *not* exposed to the LLM: it selects a function, not a signal.
    functions = sorted(registry)
    if not functions:
        raise ValueError("No run-supported functions")
    docs = [{"uri": "function:" + f, "function": f, "labels": [f],
             "descriptions": ["Engineering function " + f + " with validated run-scoped temporal coverage"],
             "text": "Engineering function " + f + " with run-scoped temporal observations"} for f in functions]
    lex = retrieval.lexical_ranking(a.question, docs)
    vectors = retrieval.embed(a.ollama_url, a.embedding_model,
                              [retrieval.concept_text(d) for d in docs], a.timeout)
    query_vector = retrieval.embed(a.ollama_url, a.embedding_model, [a.question], a.timeout)[0]
    vec = retrieval.vector_ranking(query_vector, vectors, docs)
    hyb = retrieval.fusion(lex, vec, docs, a.vector_weight)
    candidates = [docs[i]["function"] for i in hyb[:a.top_k]]
    prompt = ("Select the single engineering function explicitly supported by the question "
              "and the retrieved candidate list. If the intended function is unclear or "
              "absent, abstain. Do not guess signal IDs or mappings. "
              "Return ONLY JSON {\"engineering_function\":\"FUNCTION_OR_ABSTAIN\"}.\n"
              "Question: " + a.question + "\nCandidate engineering functions: " +
              json.dumps(candidates) + "\nReturn JSON only.")
    raw = llm.ollama(a.ollama_url, a.model, prompt, a.timeout).strip()
    import re
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.I | re.S)
    choice = json.loads(fenced.group(1) if fenced else raw)
    if not isinstance(choice, dict) or set(choice) != {"engineering_function"} or not isinstance(choice["engineering_function"], str):
        raise ValueError("Invalid structured LLM function selection")
    function = choice["engineering_function"]
    if function != "ABSTAIN" and function not in candidates:
        raise ValueError("LLM selected unsupported function")
    result = {"question": a.question, "run_id": a.run_id,
              "retrieval": {name: [docs[i]["function"] for i in order[:a.top_k]]
                            for name, order in (("lexical", lex), ("vector", vec), ("hybrid", hyb))},
              "llm_raw": raw, "selected_function": function,
              "execution": "not_requested", "aggregate": "not_computed"}
    if function == "ABSTAIN":
        result["status"] = "abstained"
    else:
        # Mandatory live GraphDB recheck before signal is exposed or queried.
        mapping = resolve_supported_mapping(a.graphdb_url, function, registry)
        result.update({"status": "mapping_validated", "mapping": mapping,
                       "operational_signal": mapping["operational_signal"]})
        if a.execute:
            validate_request(function, a.run_id, a.start_seconds, a.end_seconds, a.limit)
            graph = execute_vtkg({"engineering_function": function, "run_id": a.run_id,
                                  "start_simulation_seconds": a.start_seconds,
                                  "end_simulation_seconds": a.end_seconds, "limit": a.limit},
                                 dsn=os.environ["TEP_TIMESCALE_DSN"], graphdb_url=a.graphdb_url,
                                 mapping_discovery=a.mapping_discovery,
                                 temporal_coverage=a.temporal_coverage)
            result.update({"status": "observations_retrieved", "execution": "ok",
                           "observation_count": graph["result"]["observationCount"],
                           "truncated": graph["result"]["truncated"],
                           "vtkg_result": graph["result"], "vtkg_provenance": graph["provenance"]})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
