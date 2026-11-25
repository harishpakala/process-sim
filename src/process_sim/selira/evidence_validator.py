"""Compatibility alias for the historical correspondence implementation."""

import sys as _sys
from .correspondence import evidence_validator as _implementation

_sys.modules[__name__] = _implementation
