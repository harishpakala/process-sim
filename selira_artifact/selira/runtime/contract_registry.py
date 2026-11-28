"""Registry loading and structural validation (no policy execution)."""
import json
from pathlib import Path


def load_registry(root):
    root = Path(root).resolve()
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def read(path):
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_object)

    def artifact(value, suffix):
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ValueError("Expected relative artifact path")
        path = (root / value).resolve()
        if not path.is_relative_to(root) or path.suffix != suffix or not path.is_file():
            raise ValueError(f"Invalid artifact: {value}")
        return path

    def name(value):
        return isinstance(value, str) and bool(value.strip())

    data = read(root / "registry" / "contract_registry.json")
    if not isinstance(data, dict) or data.get("schema_version") != "1.0":
        raise ValueError("Unsupported registry schema")
    entries = data.get("contracts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Expected nonempty contract list")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid contract entry")
        key = entry.get("id")
        if not name(key) or key in seen:
            raise ValueError("Missing or duplicate contract ID")
        seen.add(key)
        kind = entry.get("kind")
        if kind not in ("SC", "LP") or type(entry.get("enabled")) is not bool:
            raise ValueError(f"Invalid kind or enabled flag: {key}")
        if entry.get("backend") not in (("shacl",) if kind == "SC" else ("ast", "sparql")):
            raise ValueError(f"Unsupported backend: {key}")
        artifact(entry.get("specification"), ".safsl")
        binding = read(artifact(entry.get("binding"), ".json"))
        if not isinstance(binding, dict):
            raise ValueError(f"Invalid binding: {key}")
        if kind == "LP":
            activation = entry.get("activation")
            if (not isinstance(activation, dict)
                    or not name(activation.get("event"))
                    or activation.get("scope") != "per_contract_instance"
                    or not name(entry.get("produces"))):
                raise ValueError(f"Invalid activation: {key}")
            if binding.get("policy_id") != key:
                raise ValueError(f"Policy binding ID mismatch: {key}")
            for direction in ("inputs", "outputs"):
                mapping = binding.get(direction)
                if (not isinstance(mapping, dict) or not mapping
                        or not all(name(k) and name(v) for k, v in mapping.items())):
                    raise ValueError(f"Invalid {direction}: {key}")
            if len(set(binding["outputs"].values())) != len(binding["outputs"]):
                raise ValueError(f"Duplicate output destinations: {key}")
    return tuple(entries)
