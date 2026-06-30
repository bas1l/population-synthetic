"""Minimal pipeline utilities.

Re-exports ``should_process_task``, the skip-if-done helper that decides
whether a pipeline step needs to run based on input/output existence and
modification times.
"""

from .pipeline import should_process_task

__all__ = ["should_process_task"]
