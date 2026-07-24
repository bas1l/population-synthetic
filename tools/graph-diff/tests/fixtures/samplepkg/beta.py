"""beta — imports alpha and core.

Edges: samplepkg.beta -> samplepkg.alpha, samplepkg.beta -> samplepkg.core.
"""

from samplepkg import alpha, core

RESULT = alpha.VALUE + core.CONSTANT


async def combine(x, y):
    """Async top-level function, for async-signature extraction tests."""
    return x + y + RESULT
