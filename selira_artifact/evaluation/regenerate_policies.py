"""Generate registered LP queries and interface manifests."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from selira.compiler.policy_sparql import compile_policy
from selira.runtime.contract_registry import load_registry
from selira.runtime.policy_evaluator import load_policy
from selira.runtime.runtime_binding import validate_binding


def regenerate(root=ROOT):
    root = Path(root)
    for entry in load_registry(root):
        if entry["kind"] != "LP" or not entry["enabled"]:
            continue
        key = entry["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ValueError("Unsafe generated artifact ID")
        source = root / entry["specification"]
        binding = root / entry["binding"]
        process = load_policy(source)
        validate_binding(process, json.loads(binding.read_text(encoding="utf-8")))
        compiled = compile_policy(process)
        folder = root / "generated" / key
        query = folder / "sparql" / (key + ".rq")
        query.parent.mkdir(parents=True, exist_ok=True)
        query.write_text(compiled["query"], encoding="utf-8", newline="\n")
        manifest = {"id": key, "specification": entry["specification"],
                    "binding": entry["binding"],
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "binding_sha256": hashlib.sha256(binding.read_bytes()).hexdigest(),
                    "query": f"sparql/{key}.rq",
                    "inputs": {name: f"i{i}" for i, name in enumerate(compiled["inputs"])},
                    "outputs": {name: f"o{i}" for i, name in enumerate(compiled["outputs"])}}
        (folder / "policy_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(key, query)


if __name__ == "__main__":
    regenerate()
