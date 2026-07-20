"""figures.py -- Shared matplotlib figure-persistence helper.

A single home for the PNG+SVG dual-format save idiom, so any chart module that
wants a vector sibling alongside its raster output does so through one function
rather than duplicating ``savefig``/``close`` pairs at each call site. Keeps the
dual-format policy (which formats, ``bbox_inches``, figure lifecycle) in one
place; callers only ever hand over a finished ``Figure`` and a target PNG path.
"""

from __future__ import annotations

from pathlib import Path


def save_figure(fig, png_path: Path, *, dpi: int) -> Path:
    """Write *fig* as a PNG+SVG pair (same stem/dir) and close it.

    Writes ``png_path`` at *dpi* and ``png_path.with_suffix(".svg")`` (SVG is
    vector and ignores ``dpi``), both with ``bbox_inches="tight"``, creating the
    parent directory if needed. Closes *fig* afterward. Returns the PNG path,
    matching the pre-existing caller contract of the chart functions that route
    through this helper.
    """
    import matplotlib.pyplot as plt

    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png_path, dpi=dpi, bbox_inches="tight")
    fig.savefig(png_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)
    return png_path
