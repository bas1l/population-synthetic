"""beta — imports alpha and core.

Edges: samplepkg.beta -> samplepkg.alpha, samplepkg.beta -> samplepkg.core.
"""

from samplepkg import alpha, core

RESULT = alpha.VALUE + core.CONSTANT
