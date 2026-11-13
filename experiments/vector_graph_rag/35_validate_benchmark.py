"""Validate Experiment 35 dataset against the local ontology index.

Run from repository root:
  python experiments/vector_graph_rag/35_validate_benchmark.py
This is dataset validation, not a GraphDB/Ollama/VTKG evaluation.
"""
import argparse
import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATEGORIES = {"concept_retrieval", "predicate_sparql", "explicit_function",
              "implicit_function", "safety_abstention"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=HERE / "data" / "engineering_questions_35.json")
    parser.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    args = parser.parse_args()
    data = json.loads(args.benchmark.read_text(encoding="utf-8-sig"))
    cases = data["cases"]
    assert len(cases) == data["question_count"] == 30
    assert len({case["id"] for case in cases}) == len(cases)
    counts = collections.Counter(case["category"] for case in cases)
    assert set(counts) == CATEGORIES and all(counts[c] == 6 for c in CATEGORIES)
    index = json.loads(args.index.read_text(encoding="utf-8-sig"))
    allowed = {c["uri"]: c["domain"] for c in index["concepts"]
               if c.get("kind") == "property" and c.get("uri")}
    for case in cases:
        category = case["category"]
        gold = case.get("gold", {})
        if category in {"concept_retrieval", "predicate_sparql"}:
            uri = gold["predicate_uri"]
            assert uri in allowed, f"{case['id']}: missing ontology URI {uri}"
            assert allowed[uri] == gold["domain"], f"{case['id']}: domain mismatch"
        elif category == "implicit_function":
            assert gold.get("function") is None, f"{case['id']}: unverified implicit gold"
        elif category == "explicit_function":
            assert gold["function"] in case["question"], f"{case['id']}: function absent"
            assert gold["provisional_signal"], f"{case['id']}: signal absent"
    print("Benchmark valid:", len(cases), "cases")
    for category, count in sorted(counts.items()):
        print(f"  {category}: {count}")
    print("Ontology targets verified against local index.")
    print("NOTE: This is dataset validation, not an end-to-end benchmark run.")

if __name__ == "__main__":
    main()
