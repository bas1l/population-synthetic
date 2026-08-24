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
rule in [Design principles](../architecture/design-principles.md).

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

`palette.HEATMAP_CMAP` is `inferno` and it is the only ramp. It is perceptually uniform, monotone
in lightness, and it matches the published manuscript tables, so the internal grids read as drafts
of the published ones rather than as a separate visual language.

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

The annotated and clean variants of a figure are the **same renderer under different policies**, so
they cannot diverge on the next edit. Where the two differ in more than the policy — the annotation
size, and the caption sentence that *describes* the policy — the three travel together in one
frozen `GridVariant` record, because a clean figure captioned "printed with the two counts it is
the quotient of" would be a figure disagreeing with itself.

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
