"""Run a manual DEXPI SHACL subgraph extraction smoke test.

From the repository root:
    python -m pip install -e .
    python try_dexpi.py
"""
import argparse
import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_subgraph import (
    extract_question,
    load_index,
)

DEFAULT_QUESTION = (
    "Show the MeasuredVariable of InstrumentationFunction "
    "and the ActuatedVariable of ActuatingFunction"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--index",
        type=Path,
        default=Path(__file__).resolve().parent
        / "semantic/ontology2/dtwise/dtwise-schema-index.json",
    )
    args = parser.parse_args()
    index = load_index(args.index, domain="dexpi")
    result = extract_question(index, args.question)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
