"""Compatibility alias for archived engineering correspondence."""

import sys as _sys
from ..legacy.correspondence import consumer_policy as _implementation

_sys.modules[__name__] = _implementation
