"""Fault injection primitives for process-sim."""

from .manager import FaultManager
from .models import Fault, FaultType

__all__ = ["Fault", "FaultManager", "FaultType"]
