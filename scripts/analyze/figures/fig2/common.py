"""Shared plumbing for the manuscript Figures 2, 5 and 6 rebuild (2026-10-04).

Paths come from the repo config (experiment_defaults.yaml -> output_base, analysis
registry -> per-process folders). Display strings come from the repo labels module,
plus the docx hand-edits recorded in LABEL_OVERRIDES. Every figure is written as
PNG (600 dpi), SVG and PDF on a fixed canvas, under the repo house rcParams.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from population_synthetic.analysis.utils import figures as _figures  # noqa: E402
from population_synthetic.analysis.utils.cap_index import load_cap_index  # noqa: E402
from population_synthetic.analysis.utils.labels import model_labels  # noqa: E402
from population_synthetic.analysis.utils.model_order import ranked_model_order  # noqa: E402
from population_synthetic.analysis.utils.registry import (  # noqa: E402
    analysis_output_dir,
    resolve_output_base,
)
from population_synthetic.analysis.utils.style import house_rc_params  # noqa: E402

COUNTRY = "swedish_02"
# FIG_OUTPUT_BASE / FIG_OUT_DIR override the read root and the write folder (to try a draft
# on a scratch copy without touching the published figures); unset = the defaults below.
OUTPUT_BASE = resolve_output_base(os.environ.get("FIG_OUTPUT_BASE") or None)
OUT_DIR = Path(
    os.environ["FIG_OUT_DIR"]
)
MANUSCRIPT_DIR = Path(os.environ["MANUSCRIPT_DIR"])
# 2026-10-20 copy: panel A is read from this folder. images/fig2.png is the docx raster with the
# income-source box recoloured (recolour_income_box.py); images/fig2_docx_original.png is the untouched one.
DOCX_IMAGES = Path(__file__).resolve().parent / "images"
PANEL_A_IMAGE = os.environ.get("FIG2_PANEL_A_IMAGE") or "fig2.png"
PNG_DPI = 600
#: 2026-10-20: EPS added beside the three earlier formats (submission format).
SUFFIXES = tuple((os.environ.get("FIG_SUFFIXES") or "png,svg,pdf,eps").split(","))

#: Model display names as the docx artwork prints them. The config labels carry no
#: version for the two Claude CLI models; the manuscript artwork adds it by hand.
LABEL_OVERRIDES = {
    "claude_haiku": "Claude Haiku 4.5",
    "claude_sonnet": "Claude Sonnet 5",
}


def adir(process_id: str) -> Path:
    return analysis_output_dir(process_id, OUTPUT_BASE)


def display_models(model_ids) -> dict[str, str]:
    names = model_labels(list(model_ids))
    names.update({m: LABEL_OVERRIDES[m] for m in model_ids if m in LABEL_OVERRIDES})
    return names


def ranked_models() -> list[str]:
    """model_ranking's published column order (the house standard model order)."""
    perf_path = adir("model_ranking") / f"{COUNTRY}_performance.json"
    with open(perf_path, encoding="utf-8") as fh:
        perf = json.load(fh)
    return ranked_model_order(perf, load_cap_index(OUTPUT_BASE))


def cap_index():
    return load_cap_index(OUTPUT_BASE)


def rc():
    """House rcParams plus a mathtext face that matches the house font (for 2^nd)."""
    params = dict(house_rc_params())
    font = params["font.family"][0]
    params.update({"mathtext.fontset": "custom", "mathtext.rm": font, "mathtext.it": f"{font}:italic",
                   "mathtext.bf": f"{font}:bold"})
    return params


def save(fig, stem: str) -> list[Path]:
    """Write <stem>.png (600 dpi), .svg and .pdf at the canvas size, then close."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    export = _figures._export_rc_params()
    with plt.rc_context(export):
        for suffix in SUFFIXES:
            path = OUT_DIR / f"{stem}.{suffix}"
            fig.savefig(path, format=suffix, dpi=PNG_DPI, bbox_inches=None, pad_inches=0)
            written.append(path)
    plt.close(fig)
    return written


def hosting_classes() -> dict[str, str]:
    """{model id: 'hosted' | 'local'} from the repo's provider-hosting config."""
    from population_synthetic.analysis.model_ranking.hosting import classify_hosting, load_hosting_config
    from population_synthetic.generators.synthetic.manifest_loader import discover_axis_values
    repo = Path(os.environ["POPSYNTH_REPO"])
    return classify_hosting(
        discover_axis_values("models"),
        load_hosting_config(repo / "config" / "analysis" / "model_ranking" / "provider_hosting.json"),
    )
