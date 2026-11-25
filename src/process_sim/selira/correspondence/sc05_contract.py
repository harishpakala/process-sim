"""Compatibility alias for archived engineering correspondence."""

import sys as _sys
from ..legacy.correspondence import sc05_contract as _implementation

_sys.modules[__name__] = _implementation
