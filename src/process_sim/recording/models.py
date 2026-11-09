"""Canonical observation and event models.

These models are storage-neutral so the recorder can later target Parquet,
a time-series storage, or a temporal knowledge graph without changing the
simulation core.
"""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class Observation:
    """A timestamped numeric process observation."""

    run_id: str
    simulation_time_hours: float
    wall_time: Optional[str]
    variable: str
    value: float
    unit: Optional[str] = None
    quality: Optional[str] = None
    source: str = "simulation"


@dataclass(frozen=True)
class Event:
    """A discrete, semantically meaningful occurrence."""

    run_id: str
    simulation_time_hours: float
    wall_time: Optional[str]
    event_type: str
    subject: str
    source: str
    predicate: Optional[str] = None
    object: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
