# Figure conventions

How every figure this repository publishes is drawn, and why. Two kinds of rule live here and they
have different force:

- **Publication constraints** come from `figure-preparation-standards.docx` in the manuscript folder
  (`Manuscripts/40_llm-population-fidelity-benchmark/`). They are not ours to choose. Each one is
  bound to a named constant in the presentation layer, so the code has exactly one copy of it and
  this page can point at the constant rather than keeping a second.
- **Labelling conventions** are ours. The standards document is silent on labelling, so the rules
  below are the project's own choices, recorded here with the sources they were adopted from.

The layer that enforces all of it is described in
[Sub-packages](../architecture/sub-packages.md) and governed by the *presentation computes nothing*
rule in [Design principles](../architecture/design-principles.md). A last section covers neither
kind of rule but the step after both: how a drawn figure becomes a *published* one in `04_Figures`,
and how it gets its number.

---

## Publication constraints

| Constraint | Where it is enforced | Named as |
|------------|---------------------|----------|
| Vector output, in a format the target venues accept | `analysis/utils/figures.py` | `OUTPUT_SUFFIXES` (`RASTER_SUFFIX` + `VECTOR_SUFFIXES`) |
| Arial, or a metric-compatible substitute | `analysis/utils/style.py` | `FONT_STACK`, resolved by `house_font()` |
| Text no smaller than the publisher's floor, no larger than the ceiling | `analysis/utils/style.py` | `FONT_FLOOR_PT`, `FONT_CEILING_PT`, and the named sizes in `FONT_SCALE` |
| Strokes above the publisher's floor | `analysis/utils/style.py` | `MIN_STROKE_PT` and the stroke ladder below it |
| 8-bit RGB, no alpha channel | `analysis/utils/style.py` | `house_rc_params()["savefig.transparent"] = False` |
| Printable canvas | `analysis/utils/style.py`, checked on write in `figures.py` | `FULL` (width) and `MAX_HEIGHT`, via `_check_canvas` |
| Manuscript text width and strip height (a manuscript rule, not a venue one) | `analysis/utils/style.py` | `TEXT_WIDTH` (456 pt) and `STRIP_HEIGHT` (150 pt); a strip's axis title is `STRIP_AXIS_TITLE`, at the floor |
| File-size ceiling | `analysis/utils/figures.py` | `MAX_FILE_BYTES`, via `_check_file_size` |
| Raster resolution | `analysis/utils/figures.py` | `RASTER_DPI` |

Read the constants for the numbers. They are documented at their definitions, and nothing in `src/`
restates them.

### Three formats, one writer

`save_figure(fig, png_path)` is the only `savefig` call site in `src/`. It writes PNG, SVG and EPS
from one `Figure`:

- **EPS is the submission artifact.** Of the four target venues it is the only format all four
  accept: PDF fails PLOS, TIFF fails TMLR, PNG fails PLOS.
- **SVG is the editing artifact** — the format a figure is opened in to annotate for the deck.
- **PNG is the reading artifact** — the format a draft is skimmed in.

A second writer, or a per-format `savefig` at a call site, was rejected in
[`plans/completed/fidelity-radar-svg-export.md`](plans/completed/fidelity-radar-svg-export.md):
the format set then drifts between call sites, which is the state — half the layer emitting vector,
half emitting raster only — that this arrangement exists to end. **Extending `save_figure` is the
only sanctioned way to add a format.**

### Vector text is text, and each backend needs telling separately

Every one of the three fonttype keys is pinned in `style.house_rc_params()` and re-installed at
write time by `figures.EXPORT_RC_KEYS`, because all three are read by their backend when the file
is written — not when the figure is drawn — and several chart modules return an unsaved `Figure`
for their driver to save under whatever ambient `rcParams` happen to be installed.

| Key | Pinned to | matplotlib's default, and what it costs |
|-----|-----------|------------------------------------------|
| `ps.fonttype` / `pdf.fonttype` | `42` | `3` — Type 3 charprocs instead of the embedded TrueType face |
| `svg.fonttype` | `"none"` | `"path"` — every glyph converted to an outline |

The two policies point in opposite directions, deliberately, because the two formats have opposite
jobs. The EPS **embeds** its face: it leaves the repository, and a venue's renderer must not need
Arial installed. The SVG **references** its face by name, so it arrives in Inkscape as real `<text>`
nodes that can be retyped — which is the whole reason the layer emits an editing artifact at all.

Under matplotlib's default the SVG delivered neither: a model x method heatmap reached Inkscape as
~1700 anonymous `<use>` shapes with no `<text>` node and no family named anywhere in the file.
The cost of the fix is that a host lacking every family in `style.FONT_STACK` substitutes one with
different metrics, which can shift or overlap tight annotations — accepted, because the SVG is the
working copy and the PNG beside it is the fixed visual reference. matplotlib offers no third
option; its `svgfont` embedding mode was removed.

Guarded by `tests/test_figures.py`, one test per direction, each pinning matplotlib's own default
first so the test states the condition it guards against.

### Budgets are checked on the written bytes, and a rejection writes nothing

All three formats are rendered to memory first. The canvas is measured from the EPS
`%%HiResBoundingBox` — the *written* extent, which `bbox_inches="tight"` decides, not
`fig.get_size_inches()`, since tight cropping both trims unused margin and grows past the figure
rectangle for any artist placed outside it. Each format's length is checked against the file
ceiling. Only then is anything written, so an over-budget figure leaves no partial output and
raises `FigureBudgetExceeded` naming what it violated.

`PAD_INCHES` is pinned to zero. matplotlib otherwise adds 0.1 in of whitespace on each side of the
tight box, which put a figure drawn exactly at the printable cap over it and made the canvas
vocabulary unreachable by construction. At zero the written canvas *is* the content extent, so it
can exceed the cap only when an artist genuinely overflows the figure rectangle — which is the case
worth failing on.

**The fixed-canvas mode.** `save_figure(fig, path, fixed_canvas=True)` writes the figure at its own
size instead of the tight box (`bbox_inches=None`). It exists for a figure laid out in absolute
points to an exact size — today the reference-method gain forest at `TEXT_WIDTH` × `STRIP_HEIGHT`.
The tight box is built from text *layout* boxes, and a rotated multi-line tick label's layout box
is wider than its ink, so the tight crop wrote that 150 pt strip 156 pt tall although nothing was
drawn past its edge. Nothing can grow in fixed mode to hold an overflowing artist, so the mode adds
one check, `_check_ink_inside_canvas`: ink on an outermost row or column of the rendered PNG, or
ink beyond the canvas in a second raster rendered over the union of the canvas and the tight box,
raises `FigureBudgetExceeded` and nothing is written. The canvas and file-size checks run
unchanged, and the default tight mode is byte-for-byte what it was.

### No transparency

matplotlib's PostScript backend has no alpha: it logs *"partially transparent artists will be
rendered opaque"* and flattens every `alpha=` artist. An EPS drawn with transparency therefore
differs from the PNG and SVG beside it — silently, and only in the one file that leaves the
repository.

The layer resolves this by **not using `alpha=` at all**. Where a colour was previously drawn
translucent, one of two things happens:

- If the layer already has a named role for the de-emphasised thing — a grid rule, a reference
  line, a faint connector — the figure draws that **role**, opaque. The role already encodes the
  intended emphasis, and this is what unified the layer's ~15 grid rules onto one colour.
- If the alpha was de-emphasising a *data* colour that has to keep its identity — a series hue, a
  categorical fill — the figure calls `palette.opaque(colour, alpha)`, which composites it onto its
  ground and returns the flat result. The arithmetic is the same "over" operator the raster
  backends apply, so the figure keeps the pixels it had while the EPS gains them.

Hatching, unlike transparency, survives: the withdrawn-cell hatch is written as a PostScript
pattern rather than dropped.

### Cells are separated, never abutted

`imshow` paints heatmap tiles edge to edge, and two touching tiles shift each other's apparent
value — simultaneous contrast, named as a defect of unseparated raster grids in Crameri, Shephard
and Heron (2020), *Nature Communications* 11:5444, citing Wong (2011), *Nature Methods* 8:441.
`render_grid` therefore strokes every interior cell boundary in the page's own colour
(`palette.CELL_STROKE` at `grids.CELL_STROKE_WIDTH`), so a cell is read against the ramp rather
than against its neighbour. The perimeter is left to the caller: several grids already draw a
frame, a tier divider or a marginal column there, and a second outline underneath one of those
reads as a doubled rule rather than as a gap.

### One ramp

`palette.HEATMAP_CMAP` is `inferno` and it is the ramp for every **magnitude** in the layer. It is
perceptually uniform, monotone in lightness, and it matches the published manuscript tables, so the
internal grids read as drafts of the published ones rather than as a separate visual language.

There is exactly one sanctioned departure, `palette.SIGNIFICANCE_CMAP` (`Blues_r`), and it exists
because a significance tier is not a magnitude. See "A tier is not a magnitude" below.

A sequential ramp orders cells by **magnitude alone**. The two quantities in the layer that are
genuinely two-sided — `realism_ranking`'s typicality statistic, read against the real population's
own value, and `method_significance`'s trend slope, read against zero — therefore carry their side
in the **annotations**: a signed number in every cell, a rule across the colourbar at the
reference, and a printed caption saying the side is not in the colour. A future two-sided heatmap
must do the same or keep its own diverging ramp; what it must not do is adopt this ramp and leave
the sign implicit, because the resulting figure looks complete while having dropped half its
content.

This is settled by
[the 2026-08-12 ADR](decisions/2026-08-12-self-contained-typicality-axis.md), which rejected a
diverging ramp. Introducing one requires an ADR superseding it.

### Discrete levels come from the ramp, not from a second palette

Some quantities are not continuous: a significance tier is one rung of a ladder a config file
declares, and painting it on a continuous scale invites reading a `p` of 0.049 as meaningfully
darker than one of 0.051. `palette.heatmap_levels(n)` returns an `n`-step resampling of a
sequential ramp — the house ramp unless the caller names another — so a binned quantity stays in a
single visual language instead of acquiring a palette of its own. It preserves `set_bad`, which is
what keeps an unpainted cell legal — `grids` raises on a colormap whose missing colour is
transparent.

Its only sanctioned use is binning an **ordered** quantity. It is not a categorical-hue source: `n`
steps of a sequential ramp read as "more" and "less", which is a lie about an unordered set.

### A tier is not a magnitude

The two `method_significance` grids — the method × method squares and the reference-method gap grid,
and only those — bin `palette.SIGNIFICANCE_CMAP` (`Blues_r`) rather than the house ramp. They are
the layer's only callers of `heatmap_levels` that pass a `name`.

The reason is what they paint. A tier is an **ordinal grade** read off a ladder a config file
declares: the rungs are ranked, but the distance between two of them is not a number. Inferno runs
black → purple → red → orange → yellow, and a hue change of that size between adjacent steps invites
reading the ladder as a set of *kinds* — the red tier, the yellow tier — when the only relation
between them is more and less. `Blues_r` is a single hue, so brightness alone carries the ordering,
and it is reversed, so the darkest step is the most significant rung (`****`) and the palest is `ns`.

The palest **painted** step also has to stay clear of `palette.MISSING_COLOR`, the unpainted
"never tested" fill, because those two states are different findings (see the four-state table
below). `Blues_r` ends at `#f7fbff`, near white and unmistakable against the `#DDDDDD` grey.
`Greys_r` was rejected for exactly this: its fourth step lands on top of that grey.

Annotation colour needs no adjustment for the change. `palette.text_color_on` asks the mappable
what it actually painted and picks white or black by WCAG relative luminance, so the two dark rungs
take white text and the three light ones black, without a threshold tuned to any one ramp.

---

## Labelling conventions

None of these is mandated by the standards document. They are the project's choices.

### Ids never reach the canvas

Every model, strategy, country and attribute id a figure displays is resolved through
`analysis/utils/labels.py`, which reads the `label:` / `display:` blocks already present in the
axis YAMLs (`config/synthetic/axes/`) plus `config/analysis/attribute_labels.yaml` for the
canonical attribute names. There is no id-to-string table in Python and no `.get(id, id)`: an
unresolvable id raises `UnknownAxisValue` naming the id and the files searched. A fallback to the
raw id was explicitly rejected — it is the banned `attr or DEFAULT` pattern, and its failure mode
is a new arm shipping as `openrouter_kimi_k3` and being caught at proofing.

Two axes are not axis ids and carry their own vocabulary, on the same terms. A **consistency
rule** declares a required `label:` beside its `id:` in
`config/analysis/consistency/{country}.yaml`; the id stays the CSV and JSON join key, the label is
what ticks, and a label containing an underscore raises at load — so a rule added by copying its id
into its label fails there rather than on a published axis. A **scanned population** —
`real_{country}`, or a run slug — resolves through `labels.population_label()`, which decomposes
the slug against the *declared* axis ids rather than splitting on `_`, because both strategy and
model ids contain underscores of their own and a naive split produces a plausible wrong pair in
silence.

### Sentence case, proper nouns preserved

`Kimi K3`, `Claude Sonnet`, `Housing tenure`. This is *Nature*'s documented standard. APA's title
case is the social-science alternative and is deliberately not adopted.

### No underscores

No journal guideline sanctions them; they are a code-identifier convention. The resolver raises on
a label containing one, so the rule cannot rot silently.

### No API-provider prefix on any axis

LMArena's leaderboard column names the model's *creator*, not its serving layer; the Kimi K2 report
and the HuggingFace leaderboard do the same. The serving layer is genuine provenance for this
project — OpenRouter can reroute quantizations, and the two Ollama hosts are different GPUs — so it
is not discarded. It moves to the generated provenance table
(`scripts/analyze/export_model_provenance.py`, from `labels.model_provenance_rows()`), which is
where HELM-style papers keep it, rather than onto the figure.

The same rule applies to a **legend**, which is where it was first broken. The hosted/local split
is a real distinction and several figures encode it in hue and marker shape, but its legend text
names the *class* and not the serving software: `table_style.HOST_LABELS` reads
`hosted (API)` / `locally served`, not `local (Ollama)`. Naming the software there was worse than
useless — it put the serving layer back on the figure, and it named the software without naming
the machine while the two local hosts are different GPUs, so the parenthetical was provenance a
reader could not act on. Every restatement of that text, the LaTeX table caption included, binds
to `HOST_LABELS` rather than repeating the string.

### Generation methods render as A–E, with the key in the graphic

The letter is the family's **rank** in `config/synthetic/axes/strategies/_families.yaml`, derived
at render time by `labels.method_letters()` and never stored — reordering that file reorders the
letters, and no Python constant has to follow.

Two properties are deliberate:

- **Letters are absolute, not dense.** A figure omitting a family shows `A` and `C` rather than
  renumbering to `A` and `B`, so two figures drawn over different arms stay readable against each
  other.
- **The version marker is a property of the id set.** v1 and v2 are distinct analysis levels the
  pipeline never pools, so a figure containing both must distinguish them. `method_letters()` sees
  the whole id set and returns a bare letter when only one version is present, and a numbered one
  (`B1`, `B2`) when both are. It is a plain digit, not a subscript: Arial carries no U+2080–2089
  glyph, so a true subscript would render as a missing-glyph box or silently pull in a second
  typeface through matplotlib's per-glyph fallback — the class of silent substitution this layer
  exists to remove. Mathtext renders, but it is matplotlib syntax and `labels.py`'s contract forbids
  it knowing a renderer exists.

**The key travels with the figure.** PLOS and Springer both require figure keys to be in the
graphic rather than deferred to the caption. `labels.method_key_lines()` supplies it; captions
repeat it. A figure that prints letters without printing the key is incomplete.

The families, simplest first, are the order `_families.yaml` declares. Read that file for the
current assignment — it is the source, and this page deliberately keeps no second copy.

---

## Annotation policy

What a heatmap cell prints is decided by an **annotation policy**
(`analysis/utils/grid_annotations.py`), never by the draw loop. A policy is handed one cell's
already-computed record and returns a string or `None`; it decides *text only* — never colour,
extent, or which cells are drawn.

Each policy declares the record keys it reads as fields, and `render_grid` validates **every** cell
record against that declaration before drawing anything. This is not defensive programming: it is a
recorded near-miss in which a lenient renderer read a cell by literal key, was handed a
differently-shaped block, and painted every cell grey and labelled it unavailable *without
raising*.

The clean and counted variants of a figure are the **same renderer under different policies**, so
they cannot diverge on the next edit. Where the two differ in more than the policy — the annotation
size, and the caption sentence that *describes* the policy — the three travel together in one
frozen `GridVariant` record (`analysis/utils/grid_variants.py`), because a clean figure captioned
"printed with the two counts it is the quotient of" would be a figure disagreeing with itself.

### The unsuffixed filename is the clean figure

Every grid family that publishes variants writes **two** files from one renderer, and the naming is
the same for all six:

| File | What a cell prints |
|------|--------------------|
| `{stem}.{png,svg,eps}` | the value alone — the **camera-ready** figure, the one the manuscript and the deck reference |
| `{stem}_with_counts.{png,svg,eps}` | the same value over the count it rests on |

The rule is one function, `grid_variants.variant_suffixes()`, so six drivers cannot drift into six
naming schemes; a driver enumerates a family's `GRID_VARIANTS` instead of naming its variants, and
adding a third publishes it without a CLI change. A family whose map carries no `clean` variant
raises rather than promoting an arbitrary one into the name every downstream reference resolves to.

**The clean figure is the default because a repeated denominator is noise.** On these grids the
count is constant down a column — every cell of a combination is measured over the same capped
population — so `n=267` in fifty cells spends a line of every cell on one number. It is not
discarded: it stays in the CSV the grid was drawn from, in the `_with_counts` sibling, and on the
row and column marginals of the grids that carry them, which print their counts in **both**
variants. A rate on a figure still never travels without a stated base; the base is simply stated
once instead of fifty times.

Two things the clean variant never drops. A **qualifier** that carries information the colour does
not — the typicality grid's signed distance to the real population, which on a sequential ramp is
the only reading of the reference's side there is — stays in every cell of both variants. And the
**real-population band**, where a figure draws one, keeps its own `n`: like a marginal, it states
the base once for the whole figure.

Because the two variants differ *only* in cell text, they are substitutable by construction —
identical rows, columns, extent, colour scale and markings — and the tests assert exactly that.
Dropping a line frees vertical room, which a variant may spend by moving one step up the house
scale; it may never be spent the other way, and no annotation goes below `FONT_FLOOR_PT`. A cell
carrying an inline qualifier is bound by the cell's *width* rather than by the line it dropped, so
it keeps its size.

### The method × method squares, and why "not tested" is not "not significant"

`method_significance` draws the sixth family: one square per analysed category plus the pooled
`overall` panel, written into `{country}_method_pair_significance/` as `{panel}.{png,svg,eps}` and
its `{panel}_with_counts` sibling. It exists because the bracket figure beside it draws only the
pairs its configured `pairs_mode` selects — four of ten on the live five-method axis — while all
ten are computed and Holm-corrected. The square shows the other six.

Its two channels are deliberately different, and that difference is the family's whole design. The
**fill** is the pair's significance tier, binned onto the config's own star ladder through
`palette.heatmap_levels` on `palette.SIGNIFICANCE_CMAP`, darkest rung most significant, and it is
*symmetric* across the diagonal. The **text** is the signed row-minus-column difference in TV
similarity, and it is *antisymmetric*. Direction therefore lives
in the annotation, per the one-ramp rule above; the sign convention itself is oriented upstream, in
`builder._method_panel`, so the renderer reads cell `(i, j)` and negates nothing. The `with_counts`
variant adds each pair's paired-block count, which is the diagnostic reading, not the published one.

Four cell states, and collapsing any two of them is a correctness failure rather than a cosmetic
one:

| State | Fill | Text |
|-------|------|------|
| tested, significant at some tier | the tier's level on the single-hue significance ramp | the signed difference and the tier's symbol |
| tested, not significant | the palest **painted** level | the signed difference and the `ns` symbol |
| never tested — a degenerate panel, or too few paired blocks | **unpainted** (`set_bad`) | the policy's `absent_text` mark |
| the diagonal — a method against itself | unpainted (`set_bad`) | nothing at all |

A pair that was never tested carries no evidence; a pair tested and reported `ns` carries evidence
of no difference. Painting the first as the second would report a finding the analysis never made,
which is why the two differ in *fill* and the diagonal is separated from both by carrying no text.
The in-figure key states each of those readings, so the distinction survives the figure leaving the
repository.

### The reference-method gap grid, and why its sign runs the other way

The squares are per category: fifteen files, each showing every method pair on one demographic
axis. `{country}_reference_method_gap` is the seventh family and the summary of them — one figure
for the whole run, rows the simpler methods, columns every analysed category with the pooled
`overall` panel last, and each cell the **reference method** against that row's method on that
category. Fill, ladder, levels and the four cell states are the squares'; there is no diagonal,
because the two axes are different things.

Two properties are the family's own.

The reference method is **derived, never named**: it is the last entry of the run's
`method_order`, the most complex method under the config-resolved complexity ordering, and it is
labelled by its letter and family phrase — so retiring a family, adding one, or running both
strategy versions re-points the figure without an edit, and the letters become `A1/A2/…` on their
own.

And its cells read **reference minus row**, the opposite orientation from the squares'
row-minus-column, because the question this figure asks is what the hardest method *gains*. The
inversion costs nothing in the renderer: `pair_matrix` already stores both orders, so the figure
reads the other index pair rather than negating anything, and the sign convention still has exactly
one home in `builder._method_panel`. Because two figures in one process folder then carry opposite
orientations, the in-figure key names this one's explicitly — it is the one place a reader could
otherwise carry an assumption from the figure beside it.

The omnibus is per column here rather than per figure, so it travels under each column heading
instead of in the title, and the test that produced it is named once in the key rather than fifteen
times — the same ink economy that puts a constant denominator in the `_with_counts` sibling. A
category whose panel is flagged `insufficient_n` keeps its column, unpainted and marked, and is
logged with the panel's own note: blanking it would drop the category from the figure's own axis
and read as "analysed, nothing separated".

---

## Publishing: how a figure reaches `04_Figures`

Drawing a figure and *publishing* one are separate acts. The presentation layer writes every figure
it draws into `03_Analysis` — some 2,100 of them across thirteen process folders — and a manuscript
cites about a dozen. Which dozen is a research decision, and it is recorded as **config**:
`config/analysis/figure_selection.yaml`, holding named sets (`manuscript`, and any other purpose).
Not as code, and not as a hand-curated folder outside the repository. Nothing is auto-discovered: a
figure is in a set because a human listed it.

### How a figure gets a number

A roster entry is three fields, plus an optional block for a figure that belongs to one combination:

```yaml
- n: 7
  name: model_x_method_heatmap
  source: "model_ranking/{country}_model_method_heatmap"
```

`source` is the **extension-less stem** of the figure as the drawing task wrote it, relative to the
analysis stage. `{country}` and `{slug}` are its only placeholders — `{slug}` available only to an
entry declaring a `slug: {model, strategy}` block, and composed through `manifest_loader.axis_slug`,
so a stem can never disagree with the folder name the producing task chose. A segment that is
neither, such as which model's panel gets published, is written out as a literal, because it is
itself a research decision and belongs in the roster.

`n` is the manuscript figure number: it orders `numbered/` and it names the file, as
`F{n:02d}_{name}`. It is **a unique integer within the set — not a position**, and two entries sharing
it raise. That is the whole contract, which is why the deck's "Figure 26b" — the linear-x variant of
the cost-vs-fidelity scatter, drawn beside it by the same task — is `n: 27` in the roster rather
than a sub-number the schema has no room for. If the manuscript ever needs a real Figure 27, that
entry renumbers and the new one takes the number.

### How `04_Figures` is produced

`figure_selection`, the **terminal** node of the analysis DAG, copies the bytes:

```
python scripts/analyze/select_figures.py --country-id swedish_02 --set manuscript
```

It computes nothing, imports no chart module and makes no publication decision — it is downstream of
the presentation boundary, not part of it — and `03_Analysis` is read-only to it. It ships
`enabled: false` in the GUI workflow, because a sweep should not fail at its last step over a roster
nobody has curated yet.

Per country and set it emits the same figures twice:

```
04_Figures/{country}/{set}/
  as_generated/   overview.{png,svg,eps}
  numbered/       F02_reference_category_proportions.{png,svg,eps}
  _index.json
```

`as_generated/` is the traceability naming — a staged image is matched back to the task that drew it
by name alone. `numbered/` is the citation naming. Both carry **every** published format, taken from
`figures.OUTPUT_SUFFIXES`, the same constant `save_figure` writes from, so the EPS the venues accept
cannot be the one left behind — which is precisely what hand-copying left behind.

Resolve-all, validate-all, **then** copy. An unknown set, an unregistered process id, a stem with
nothing behind it, a figure present in fewer than every format, a duplicate `n` or a colliding
destination basename each raise before a byte moves, and every missing figure is named rather than
only the first, so a run that is going to fail leaves the figures stage exactly as it found it. The
partial format set is the failure worth knowing: it means the task that drew that figure has not
been re-run since the presentation layer landed, and the fix is to redraw it — never to publish the
PNG on its own.

`_index.json` is written last, so its presence is the completion marker. It records `output_base`,
country, set and run timestamp, and per entry per format the resolved source path, size, mtime and
SHA-256 — enough to detect that a re-run analysis stage has moved out from under a published set
without re-reading that stage. Re-runs overwrite what they publish; a destination file the current
roster no longer claims is reported at WARNING and left in place, unless `--force` clears the set's
two naming folders first.

Staging the result onward — into the manuscript or the deck — stays manual. `04_Figures` is the
deliverable.

---

## Sources

- `figure-preparation-standards.docx` — in the manuscript folder under
  `Manuscripts/40_llm-population-fidelity-benchmark/`
- Crameri, Shephard and Heron (2020), *Nature Communications* 11:5444 — colour in science
  communication
- Wong (2011), *Nature Methods* 8:441 — colourblind-safe categorical palettes
- WCAG 2 contrast ratios — the relative-luminance crossover `palette.text_color_for_rgb` uses
- [`decisions/2026-08-12-self-contained-typicality-axis.md`](decisions/2026-08-12-self-contained-typicality-axis.md)
  — the sequential-ramp-only decision
- [`plans/completed/fidelity-radar-svg-export.md`](plans/completed/fidelity-radar-svg-export.md) —
  the one-`savefig`-idiom rationale
