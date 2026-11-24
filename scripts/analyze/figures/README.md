# Figure builders (manuscript figures 1 to 7)

Builders for the manuscript figures, drawn from the latest dataset: the ref-v3 reference
population (`real_swedish_02`) and the `swedish_02` populations of the five `*_v2` strategies
(code at tag `ref-v3-2026-11-24`).

- They run **outside the package**, in a working folder of the project data. Nothing in the
  package imports them. They were byte-compiled when added, not run.
- One folder per figure, because every folder has its own `common.py`. Only the builder
  and the modules it imports are included. Logs, caches, `out/` folders, raster images and
  data files are left out.
- `fig1/publish_fig1.py` builds Figure 1; `fig2/publish_fig2.py` Figure 2; `fig3/publish_fig3.py`
  Figure 3; `fig5/fig5_noC.py` Figure 5; `fig4_fig7/fig4.py` and `fig7.py` Figures 4 and 7.
- Figure 6 (`fig6/`): `fig6_composite.py` with `fig6_heatmap.py`, `protos.py`, `common.py`
  and `figs_common.py`. The labelled-answers workbook it reads is data and is not included;
  its label column is named `author_label`.

## Paths

Machine paths are environment variables with no default:

| Variable | Meaning |
|---|---|
| `POPSYNTH_REPO` | Root of a checkout of this repository (config files are read from it). |
| `FIG_OUT_DIR` | Folder the figures are written to (`fig2`, `fig5`, `fig6`, `fig4_fig7`; the figure 1 and 3 builders take an output folder argument). |
| `MANUSCRIPT_DIR` | Manuscript folder read by `fig2`, `fig5` and `fig6` `common.py`. |
| `DATA_DIR` | Project data folder (`fig6/common.py`: analysis outputs and the answer labels). |
| `FIG_OUTPUT_BASE` | Optional: overrides the analysis output root. |

Run from the figure's folder with the conda environment of the project and the repository
installed in editable mode, with `PYTHONIOENCODING=utf-8`.
