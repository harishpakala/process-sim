"""Fault injection primitives for process-sim."""

# Created: 2026-08-19
# Author: Harish

from .manager import FaultManager
from .models import Fault, FaultType
from .scenario import Scenario

__all__ = ["Fault", "FaultManager", "FaultType", "Scenario"]
