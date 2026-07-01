"""Skip-if-done logic for pipeline tasks.

Defines ``should_process_task``, which decides whether a task should run:
it returns ``False`` if any input is missing, ``True`` when forced or when
an output is missing, and otherwise compares modification times so a task
re-runs only when its inputs are newer than its outputs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Union

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]
PathInput = Union[PathLike, List[PathLike], None]


def should_process_task(
    *,
    output_paths: PathInput,
    input_paths: PathInput,
    force: bool = False,
) -> bool:
    def _normalize(targets: PathInput) -> List[Path]:
        if targets is None:
            return []
        if isinstance(targets, (str, Path)):
            return [Path(targets)]
        return [Path(p) for p in targets]

    outputs = _normalize(output_paths)
    inputs = _normalize(input_paths)

    for path in inputs:
        if not path.exists():
            logger.warning("Input file '%s' is missing. Cannot process task.", path)
            return False

    if force:
        logger.info("Forced processing requested.")
        return True

    for path in outputs:
        if not path.exists():
            logger.info("Output '%s' missing. Processing required.", path.name)
            return True

    try:
        oldest_output_mtime = min(p.stat().st_mtime for p in outputs)
        newest_input_mtime = max(p.stat().st_mtime for p in inputs)
    except ValueError:
        return True

    if newest_input_mtime > oldest_output_mtime:
        logger.info("Inputs are newer than outputs. Re-processing.")
        return True

    logger.debug("Artifacts up-to-date.")
    return False
