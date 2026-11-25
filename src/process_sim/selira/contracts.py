"""Compatibility alias for the historical correspondence implementation."""

import sys as _sys
from .correspondence import contracts as _implementation

_sys.modules[__name__] = _implementation
