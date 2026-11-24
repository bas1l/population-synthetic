"""Minimal pipeline utilities.

Re-exports ``should_process_task``, the skip-if-done helper that decides
whether a pipeline step needs to run based on input/output existence and
modification times, and the ``atomic_write_*`` helpers that give every
durable overwrite an all-or-nothing guarantee.
"""

from .atomic_io import atomic_write_json, atomic_write_text
from .pipeline import should_process_task

__all__ = ["atomic_write_json", "atomic_write_text", "should_process_task"]
