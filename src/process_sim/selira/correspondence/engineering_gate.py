"""Compatibility alias for archived engineering correspondence."""

import sys as _sys
from ..legacy.correspondence import engineering_gate as _implementation

_sys.modules[__name__] = _implementation
