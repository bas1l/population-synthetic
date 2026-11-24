# Compact typicality-distribution figure: 14 proposals

The data is the first-round integer typicality score from the judge, counting only personas that a majority of rounds judged able to exist. There are 58 model × method combinations, of which two were withdrawn: DeepSeek-R1 14B with method E and Gemma4 E4B with method E. The reference is the SCB real population: n = 100, median 4, 57 % scoring 4 or less.

All 14 prototypes are 456 pt wide, drawn in absolute points and written by the house `save_figure(fixed_canvas=True)`, so the canvas and ink checks ran on each one. Only the PNG is kept: after each save the SVG and EPS siblings were deleted. Width was checked from the PNG itself: 1900 px ÷ 300 dpi × 72 = 456.0 pt for every file.

The current figure being replaced is 456 × 625 pt.

To regenerate: `python protos.py [P01 P04 ...]`. The data and statistics are computed in `common.py`.

## Facts checked in the data before drawing

- **Every combination sits above SCB.** The mean shift is greater than 0 in all 58 cells (asserted in `protos.py`).
- **Median.** E has the lowest medians: 6 in 8 of its 10 combinations and 7 in the other 2. A to D have medians of 8 to 10 in 38 of their 48 combinations.
- **Tail below 5.** No combination reaches SCB's 57 % scoring 4 or less. The highest is 37 % (GPT-OSS 120B, method E).
- **Wasserstein-1 distance to SCB, per method:** B averages 4.47, C 4.16, D 3.92, A 3.62 and E 2.10. B is the furthest from SCB and E the nearest.

## Ranked recommendation

| Rank | Id | Height | Encoding | What it keeps | What it loses or risks | Precedent | Fit with house rules |
|---|---|---|---|---|---|---|---|
| 1 | **P01** | 270 pt | ECDF glyph grid, 5 × 12 plus SCB. Each cell shows the combination's ECDF, SCB's ECDF dashed on top, the gap between them shaded, and the W1 value printed | The full distribution of every cell, with the reference overlaid in each cell. The shaded area *is* the printed W1, so picture and number agree. All five key messages are visible | Readers who have not met ECDFs need one caption sentence. The mode is harder to see than in a histogram | Gleicher et al. 2011 (superposition inside a juxtaposed grid) https://graphics.cs.wisc.edu/Papers/2011/GAWJHR11/paper.pdf ; Wilke ch. 8 https://clauswilke.com/dataviz/ecdf-qq.html | Full. No ramp is used, withdrawn cells are crossed out, and all text is 8 pt or larger |
| 2 | **P06** | 228 pt | Heatmap coloured by median, with the IQR printed in each cell. SCB column reads "4 / 1–6" | Location and spread, and it is ordinal-valid (quantiles need no equal-interval assumption). "B = 9 / 9–9" shows the collapse at 8–9, and "Kimi D 6 / 3–6" shows the low tail | Shape beyond the quartiles, and integer quantiles tie often | Kay et al. 2016 https://dl.acm.org/doi/10.1145/2858036.2858558 ; Correll & Gleicher 2014 https://graphics.cs.wisc.edu/Papers/2014/CG14/Preprint.pdf | Full: `render_grid` with a one-off two-line policy (`MedianIQRPolicy`, scratch only) |
| 3 | **P04** | 218 pt | Heatmap of W1 (earth mover's distance) to SCB in score points, value printed, SCB = 0 | The most compact option. The whole-distribution distance carries every message: the E row is dark, the B row is brightest, Kimi D is 1.9, and SCB is at 0 | Shape. It assumes equal score intervals and has no sign (the "all above SCB" note on the canvas covers the sign) | Santurkar et al. 2023 (1 − W1 for LLM vs human opinion distributions) https://arxiv.org/abs/2303.17548 ; Cha & Srihari 2002 https://cedar.buffalo.edu/~srihari/papers/PRJ02-DM.pdf | Full. It is a magnitude on inferno |
| 4 | P02 | 270 pt | Mini-histogram grid: bars coloured by score, √-scaled height, SCB histogram as a black outline in every cell | The most intuitive shape, and the 8–9 spike is obvious | The SCB outline is faint against bars about 2.4 pt wide. Height is √-scaled. The colour repeats the x position | Tufte sparklines https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/ ; Perin et al. 2014 Bertifier https://aviz.fr/wiki/uploads/Bertifier/bertifier-authorversion.pdf | Full. The discrete score ramp is the same as in the current figure |
| 5 | P13 | 303 pt | Histogram heatmap: one 11-row block per method (score 0 at the bottom, 10 at the top) × 12 models, plus an SCB column in each block; fill = share on a √ scale | The full distribution on the single ramp, with no glyph arithmetic | Colour is the least accurate channel (Cleveland & McGill). Rows are 3.4 pt tall and the white cell strokes are heavy. Slightly over the 300 pt target | Sopan et al. 2013 http://www.cs.umd.edu/~ben/Sopan2013Exploring.pdf ; Cleveland & McGill 1984 http://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf | Full, with a nonlinear norm (`PowerNorm` 0.5) that must be stated |
| 6 | P05 | 218 pt | Heatmap of the share scoring 4 or less, with SCB's own 57 % in the reference column on the same ramp | The most literal "nobody reaches SCB" (57 is the only bright cell). The E row and the Kimi/DeepSeek A and D tails stand out | Everything at 5 and above. B is indistinguishable from C | Heiberger & Robbins cut-point logic https://www.jstatsoft.org/v57/i05/ | Full |
| 7 | P09 | 252 pt | Single panel, models as columns, 5 offset intervals per model (median marker, IQR bar, 10–90 % whisker), SCB IQR band across the plot | Position encoding, the most accurate channel | Busy: 58 intervals plus markers | Kay et al. / ggdist https://mjskay.github.io/ggdist/articles/slabinterval.html | Mostly. Methods are shown by marker shape plus the key, and E is filled |
| 8 | P10 | 250 pt | Thin diverging stacked bars, 5 per model, centred on the cut between 4 and 5, SCB bar and a 57 % rule | The full composition, with the balance around SCB's median directly visible | Bars 4.5 pt wide. Eleven inferno shades are hard to tell apart (and worse in grayscale) | Heiberger & Robbins 2014 https://www.jstatsoft.org/v57/i05/ | Mostly. Only the first model group carries the A–E letters |
| 9 | P03 | 280 pt | The same diverging bars as P10, laid out as a 5 × 12 glyph grid, with an SCB 57 % tick in every cell | Grid layout plus composition | The reference tick floats between rows, and the same 11-shade problem as P10 | Heiberger & Robbins 2014 | Full |
| 10 | P07 | 218 pt | Heatmap of \|Cliff's δ\| against SCB, with the signed δ printed | An ordinal effect size, with the side shown by the printed sign as the house rule requires | Every value is positive, so the sign carries no information here. "+0.50" nearly fills a 26 pt cell | Cliff 1993; Santurkar et al. for the LLM-vs-human framing | Full (`SignedValuePolicy`) |
| 11 | P12 | 174 pt | Twelve sparkline panels, one per model: share scoring 4 or less across A→E, SCB level dashed | The method trend within each model, and the jump at E | Only one statistic. The x axis is methods, which departs from the rows = methods convention | Tufte sparklines and slopegraphs https://www.edwardtufte.com/notebook/slopegraphs-for-comparing-gradients-slopegraph-theory-and-practice/ | Partial |
| 12 | P14 | 128 pt | Five ECDF panels, one per method, with 12 host-coloured model curves and SCB in bold | Smallest canvas, and the E shift is clear | Model identity (unlabelled curves) | Wilke ch. 8 | Breaks the models-as-columns rule |
| 13 | P08 | 218 pt | Heatmap of total-variation distance to SCB | Nothing that W1 does not keep better | TV ignores order, so it is the wrong metric for an ordinal score | Cha & Srihari 2002 (on why TV is unsuited to ordinal data) | Full, but not recommended |
| 14 | P11 | 116 pt | Five ternary panels over the bins 0–4, 5–7 and 8–10, with SCB as a star | E clustering visibly nearer SCB | Model identity, and the bin edges are arbitrary | ggtern https://cran.r-project.org/web/packages/ggtern/ggtern.pdf | Breaks the models-as-columns rule |

**Recommendation.** P01 is the best single replacement: 270 pt against 625 pt, with no pooling and each full distribution shown against SCB. If the text must be the more readable of the two, use P06 (228 pt).

A heatmap figure plus an in-text table was also considered: P04 or P06 in the manuscript, with P01 or P13 as the supplementary full-distribution figure. It is not the recommended route.

## Caveats (every prototype)

- **Scratch-only code.** Figures draw through the presentation layer (`style`, `palette`, `labels`, `grids`, `grid_annotations`, `figures`). `MedianIQRPolicy` and the glyph-cell drawing are scratch code, not layer modules.
- **RGBA output.** The PNGs come out RGBA from the house writer (the alpha is fully opaque). That is the writer's behaviour, not something this prototype introduced.
- **SCB label.** The SCB column is labelled "SCB (real)" as a scratch string. `labels.py` has no label that names SCB, the same gap `figs_columns.py` records.
- **W1 assumes equal intervals.** Its "score points" unit treats the gap between adjacent scores as equal. That is stronger than the ordinal premise, and a caption should say so.

## Addendum: square (Cartesian) equivalents of P11

The square and the triangle encode the same two free shares; the square uses ordinary axes. x = share scoring 0–4, y = share scoring 8–10, and the 5–7 share is 1 − x − y (distance below the diagonal). The grey triangle x + y > 1 is impossible; the diagonal is "no 5–7 scores". Code: `protos_square.py` (reuses `common.py` and `protos.save_figure`). Both are 456 pt wide (1900 px ÷ 300 dpi × 72), PNG only.

| Id | Height | Encoding | Notes |
|---|---|---|---|
| P15 | 152 pt | Five unit squares, methods A–E; one host-tinted point per combination; SCB star in each | Same information as P11 with ordinary 0 / 0.5 / 1 axes. Model identity is lost. Breaks the models-as-columns rule |
| P16 | 322 pt | One 280 pt square: A–D points in grey, one host-tinted arrow per model from its A–D mean to its E point, labels in a leader column right of the cluster; DeepSeek-R1 14B and Gemma4 E4B (E withdrawn) as open A–D-mean circles | Keeps model identity. A–D are pooled to a mean. Leader lines cross arrows in the dense lower-left |

Observations (10 models with an E point):

- **E moves more down than right.** From the A–D mean to E, the 8–10 share falls by 0.41 on average (0.74 → 0.33) while the 0–4 share rises by only 0.22 (0.03 → 0.25).
- **No E point reaches SCB's x = 0.57.** E's 0–4 share ranges 0.15–0.37; per model E closes 26–63 % of the A–D-mean-to-SCB gap along x (GPT-OSS 120B 63 %, Mistral Medium 3.5 57 %).
- **E overshoots on the middle band.** E's mean 5–7 share is 0.42 against SCB's 0.24 (A–D means 0.14–0.33): the mass leaving 8–10 lands mostly in 5–7, not in 0–4.

## Addendum (unranked): grid with a ternary triangle column

Both figures add one extra column after the SCB column. It holds one small ternary triangle per method row, using the bins 0–4 / 5–7 / 8–10 from P11. The combinations are dots tinted by hosting class and SCB is a star. The 8–10 corner is labelled only on the top triangle and the 0–4 / 5–7 corners only on the bottom one; the bin edges are also given in the legend line.

Points carry **no model label**. A 2.2 pt dot cannot hold a legible number at the 8 pt floor, and the triangle's job is to show where each method's cluster sits relative to the SCB star. Model identity stays in the grid to the left. Regenerate both with `python p17.py`.

| Id | Id | Height | Encoding | What it keeps | What it loses or risks | Precedent | Fit with house rules |
|---|---|---|---|---|---|---|---|
| add | **P17** | 282 pt | P02's mini-histogram grid (proposal #4) plus the triangle column. Cells narrowed from 26 to 23 pt; triangle side 33.5 pt (29 pt tall in a 32 pt row); dots 2.2 pt; SCB star 5 pt | Full per-cell shape, plus a summary of each method against SCB. The E cluster visibly moves toward the star while A–D hug the 8–10 edge | Triangles are small: dots overlap where models coincide (A–C near the apex), and no dot can be read back to its model | Gleicher et al. 2011 (juxtaposition plus explicit summary) https://graphics.cs.wisc.edu/Papers/2011/GAWJHR11/paper.pdf ; ggtern https://cran.r-project.org/web/packages/ggtern/ggtern.pdf | Full. All text is 8 pt or larger |
| add | **P18** | 260 pt | Alternative reading of "#4": P04's Wasserstein heatmap plus the triangle column. Cells 23 × 30 pt; triangle side 31.2 pt (27 pt tall); dots 2.2 pt | The same distance numbers as P04, with the triangle adding *which way* each method's mass is distributed | The same small-triangle compromise as P17. The heatmap cells lose 3 pt of width, but 8 pt values still fit | Santurkar et al. 2023 https://arxiv.org/abs/2303.17548 ; ggtern | Full |
| add | **P19** | 254 pt | The chosen P17 redrawn with **square** 26.5 × 26.5 pt grid and SCB cells. The width came from narrower gaps (1.5 pt between columns, 6 pt before SCB, 5 pt before the triangles, 6 pt before the colourbar) and from moving the colourbar label to a short "Score" title on top. Triangle side 27.1 pt (23.5 pt tall), dots 2.2 pt, SCB star 5 pt | Everything in P17, 28 pt shorter, with square cells whose aspect is the same everywhere | The triangles are about 19 % smaller than P17's, so dots near the 8–10 corner overlap more in rows A–C. The bottom corner labels are centred on the corners and sit close to the SCB label and the colourbar, but do not touch either. The histogram bars are 26.5 pt tall instead of 32 pt | as P17 | Full. All text is 8 pt or larger |
| add | **P20** | 280 pt | P19 with the model names and "SCB (real)" moved above the grid. Labels are at exactly 90°, read bottom to top, centred on their column, sit 2 pt above the top row, and keep the hosted/local tints. The bottom tick labels are gone. Legend, triangle caption and method key sit below the grid. Cells stay square at 26.5 pt; triangle side 27.1 pt, dots 2.2 pt | Everything in P19, with the column labels read without turning the head diagonally, next to the rows they name | 26 pt taller than P19. Vertical labels reserve a 76 pt band sized by the longest name ("Mistral Medium 3.5"). The top "8–10" corner label and the "Score" title sit at label height, but in the free triangle and colourbar columns, so nothing overlaps | as P17 | Full. All text is 8 pt or larger |
