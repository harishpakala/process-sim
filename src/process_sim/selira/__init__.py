"""Evidence-qualified correspondence contracts for SELiRA.

This package does not assert that an existing GraphDB reference is validated.
"""

# Created: 2026-10-28
# Author: Harish
from .resolution import resolve_correspondence
from .consumer_policy import authorize_use

__all__ = ["resolve_correspondence", "authorize_use"]
