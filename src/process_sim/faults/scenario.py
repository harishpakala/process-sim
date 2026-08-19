"""Scenario definitions and YAML/JSON loading for fault experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Fault, FaultType


@dataclass(frozen=True)
class Scenario:
    """A reproducible collection of scheduled faults and run metadata."""

    name: str
    faults: tuple[Fault, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        """Build a scenario from a JSON/YAML-compatible mapping."""
        name = data.get("scenario") or data.get("name")
        if not name:
            raise ValueError("scenario requires a 'scenario' or 'name' field")

        faults = []
        for item in data.get("faults", []):
            fault_type = FaultType(item["type"])
            faults.append(
                Fault(
                    fault_id=item.get("id", f"fault-{len(faults) + 1}"),
                    fault_type=fault_type,
                    target=item["target"],
                    magnitude=item.get("magnitude"),
                    value=item.get("value"),
                    start_time_hours=float(item.get("start", 0.0)),
                    duration_hours=(
                        float(item["duration"]) if item.get("duration") is not None else None
                    ),
                    metadata=item.get("metadata", {}),
                )
            )

        return cls(name=name, faults=tuple(faults), metadata=data.get("metadata", {}))

    @classmethod
    def from_file(cls, path: str | Path) -> "Scenario":
        """Load a scenario from YAML or JSON."""
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise ImportError(
                    "YAML scenarios require PyYAML; JSON scenarios need no extra dependency."
                ) from exc
            data = yaml.safe_load(text)
        else:
            raise ValueError("scenario file must use .json, .yaml, or .yml")
        if not isinstance(data, dict):
            raise ValueError("scenario document must contain an object/mapping")
        return cls.from_dict(data)
