"""alpha — imports core (edge: samplepkg.alpha -> samplepkg.core)."""

from samplepkg import core

VALUE = core.CONSTANT


class Alpha:
    """A tiny class with one method, for signature-extraction tests."""

    def scaled(self, factor: int) -> int:
        return VALUE * factor
