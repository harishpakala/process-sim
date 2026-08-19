"""Fault injection primitives for process-sim."""

from .manager import FaultManager
from .models import Fault, FaultType
from .scenario import Scenario

__all__ = ["Fault", "FaultManager", "FaultType", "Scenario"]
