"""Declarative experiment specifications and expected ground truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExpectedFault:
    """Expected fault label for a controlled experiment."""

    fault_type: str
    target: str
    start_time_hours: float
    duration_hours: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpectedFault":
        start = data.get("start", data.get("start_time_hours", 0.0))
        duration = data.get("duration", data.get("duration_hours"))
        return cls(
            fault_type=str(data["type"]),
            target=str(data["target"]),
            start_time_hours=float(start),
            duration_hours=None if duration is None else float(duration),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.fault_type,
            "target": self.target,
            "start": self.start_time_hours,
        }
        if self.duration_hours is not None:
            result["duration"] = self.duration_hours
        return result


@dataclass(frozen=True)
class GroundTruth:
    """Expected outcome labels associated with an experiment."""

    fault: ExpectedFault | None = None
    affected: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GroundTruth":
        data = data or {}
        fault_data = data.get("fault")
        return cls(
            fault=None if fault_data is None else ExpectedFault.from_dict(fault_data),
            affected=tuple(str(item) for item in data.get("affected", ())),
            related=tuple(str(item) for item in data.get("related", ())),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "affected": list(self.affected),
            "related": list(self.related),
        }
        if self.fault is not None:
            result["fault"] = self.fault.to_dict()
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True)
class Experiment:
    """A reproducible scenario execution specification."""

    experiment_id: str
    scenario: str
    seed: int | None = None
    duration_hours: float = 1.0
    ground_truth: GroundTruth = field(default_factory=GroundTruth)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("experiment_id must not be empty")
        if not self.scenario.strip():
            raise ValueError("scenario must not be empty")
        if self.duration_hours < 0:
            raise ValueError("duration_hours must be >= 0")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Experiment":
        experiment = data.get("experiment", data)
        return cls(
            experiment_id=str(experiment["id"]),
            scenario=str(experiment["scenario"]),
            seed=None if experiment.get("seed") is None else int(experiment["seed"]),
            duration_hours=float(experiment.get("duration_hours", experiment.get("duration", 1.0))),
            ground_truth=GroundTruth.from_dict(data.get("expected", experiment.get("expected"))),
            metadata=dict(experiment.get("metadata", data.get("metadata", {}))),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "Experiment":
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml
            except ImportError as exc:
                raise ImportError("YAML experiments require PyYAML") from exc
            data = yaml.safe_load(text)
        elif path.suffix.lower() == ".json":
            import json
            data = json.loads(text)
        else:
            raise ValueError("experiment files must be .yaml, .yml, or .json")
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": {
                "id": self.experiment_id,
                "scenario": self.scenario,
                "seed": self.seed,
                "duration_hours": self.duration_hours,
                "metadata": dict(self.metadata),
            },
            "expected": self.ground_truth.to_dict(),
        }
