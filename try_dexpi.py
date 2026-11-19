"""Run a manual single-domain SHACL subgraph extraction smoke test.

From the repository root:
    python -m pip install -e .
    python try_dexpi.py
    python try_dexpi.py --domain ecad --connect
    python try_dexpi.py --domain ecad --connect "Show Address of EndPoint belonging to Device in ECAD"

Note: --connect uses the experimental directed-anchor search. It does not
yet disambiguate repeated shape names using natural-language parent context.
"""
import argparse
import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_subgraph import (
    extract_question,
    load_index,
)

DEFAULT_QUESTIONS = {
    "dexpi": (
        "Show the MeasuredVariable of InstrumentationFunction "
        "and the ActuatedVariable of ActuatingFunction"
    ),
    "ecad": "Show Address of EndPoint belonging to Device in ECAD",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="Natural-language schema question")
    parser.add_argument(
        "--domain", default="dexpi",
        help="Single schema domain in the index (default: dexpi; e.g. ecad)",
    )
    parser.add_argument(
        "--connect", action="store_true",
        help="Attempt directed shortest-path connections between grounded anchors",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path(__file__).resolve().parent
        / "semantic/ontology2/dtwise/dtwise-schema-index.json",
    )
    args = parser.parse_args()
    question = args.question or DEFAULT_QUESTIONS.get(args.domain)
    if question is None:
        parser.error("Supply a question for this domain")

    index = load_index(args.index, domain=args.domain)
    result = extract_question(index, question, connect=args.connect)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
