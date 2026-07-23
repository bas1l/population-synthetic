# Brainstorm: Individual Persona Realism Judge (LLM-as-judge)

**Started:** 2026-07-23   **Last matured:** 2026-07-23   **Status:** Handed off → docs/development/plans/pending/persona-realism-judge.md

## Real goal (north star)
Rank each (model × strategy) combination — plus the SCB-sampled population as one more
competitor — on **individual persona quality**: how believable/coherent each *single* persona
is as a human, where there is no ground-truth person to compare against. This is a new analysis
task, scoped as a child of the "individual persona quality" branch only. The population-level
distributional branch (already served by `fidelity/` + `model_ranking/`) and the metadata/cost
branch are siblings, NOT part of this task.

## Where it stands
Key reframe: individual coherence is orthogonal to distributional fidelity. SCB wins distribution
by construction (sampled from real tables) but may lose individual coherence (samples filtered
marginals with weak joint links → can emit incoherent individuals, e.g. 19-year-old with a
doctorate + 40 yrs work history). The LLM judge's unique contribution is measuring the individual
coherence axis that statistics can't. Expected headline finding: a decoupling — SCB strong on
distribution, possibly weak on individual coherence; some LLM strategy trading distribution for
more coherent individuals.

## Decisions
- **All personas are bare demographic attribute tuples** on every side (LLM combos AND SCB). No
  name, no life narrative. So representation is trivially fair, and "individual quality" reduces to
  one thing: **internal coherence** — can this set of attributes describe one real person?
- **Measurement primitive: pointwise coherence-flagging** (revised away from pairwise). Show the
  judge ONE rendered tuple; ask it to list any attribute pairs that contradict each other for a
  single real person, with a severity. Aggregate per combination → an **incoherence rate**
  (fraction with ≥1 clash) + severity/type breakdown = the ranking (lower is better). Rationale
  (which pair clashed) falls out for free. SCB gets an incoherence rate too — headline is concrete:
  "the real-table sampler emits X% incoherent individuals because chained sampling doesn't condition
  on age↔education; best LLM strategy emits Y%".
  - Why not pairwise: coherence is objective world-knowledge, not aesthetic; two coherent tuples
    have no coherence-based winner, so pairwise falls back on **typicality** — which is already the
    job of `fidelity/` + `multivariate_fidelity/`, and would penalize rare-but-valid real people.
  - What it gives up: can't rank two fully-coherent combinations apart. That distinction IS the
    distribution branch's job, deliberately out of scope here.

## TWO dimensions per persona (the core design)
Individual quality is NOT one number. The judge emits two orthogonal outputs per round, and they
must never be collapsed:
1. **Possibility (hard, binary)** — `can_exist`: could this attribute set be ONE real person?
   Grounded in biological/legal/temporal constraints (= the S3 "impossible" flag). Aggregate →
   **impossibility rate** per combination. Lower is better, unambiguous.
2. **Typicality (soft, 0–10)** — among people who COULD exist, how ordinary vs. unusual is this one?
   NAMING IS LOAD-BEARING: call it **typicality**, NOT "realism". Low typicality = unusual-but-valid
   = the generator reaching the real population's tails = a GOOD thing (spectrum breadth). If it were
   labeled "realism", low scores would read as bad and the whole finding inverts.

Gating rule: **dimension 1 gates dimension 2.** Typicality dispersion is measured ONLY over personas
with `can_exist = true` — otherwise a garbage generator emitting random tuples would look "broad".

## The spectrum statistic (user's central insight)
"Broad spectrum" is the **dispersion** of typicality across the population (variance / entropy /
low-typicality-tail coverage), NOT the mean. Methods stuck in "probability world" cluster at high
typicality → low dispersion. SCB + rich methods spread to the tails → high dispersion.
- Rigor correction: target is **matching SCB's dispersion**, not maximizing spread. Observed problem
  is LLM **mode collapse** (under-dispersion; citable, fits the lit dossier). "Broader is better"
  holds empirically only because everyone's currently too narrow. Report as **distance from SCB
  dispersion**, not raw spread.

## Headline output: a 2D map
x = impossibility rate (coherence cost) · y = typicality dispersion vs SCB (spectrum breadth).
Story: SCB + complex methods pay a little coherence to reach the tails; simple methods are coherent
but mode-collapsed. SCB competes as just another point.

## Justification vs existing multivariate stats
The LLM judge is non-redundant because it brings **external world knowledge** (legal/biological/
life-course constraints) the statistical pipeline lacks: multivariate fidelity can only score joints
that SCB actually fetched; the judge catches impossibilities in UNFETCHED joints — exactly the
"tables lack links" failure mode. SCB's only route to incoherent individuals is unfetched joints.

## Alternatives considered & dropped
- Pairwise / Bradley–Terry ranking — dropped: re-measures typicality under the name of realism.
- Pointwise 1–5 realism score — dropped: calibration drift + blandness bias.
- Reference-anchored — parked: only "real" anchor is SCB, the thing under test.

## Threads explored
- Scope narrowed to individual-quality judge only (kept). Population/metadata branches out of scope.
- No ground truth for individuals → "realism" = internal coherence + plausibility, not accuracy (kept).
- Blandness-bias trap: naive scoring rewards typical personas, penalizes rare-but-valid ones (open).

## Typicality source: LLM-judged (settled)
Typicality is LLM-judged, NOT statistical SCB-density. Statistics operate ON the judge's outputs
(aggregating scores across rounds/personas), not by reaching back to the SCB tables. The
statistical-density alternative is dropped.

## Aggregation ladder (stats on top of LLM output)
Nested structure: **N rounds ⊂ persona ⊂ combination (N tunable, default 3).** This nesting IS where the stats live.
- N = judge rounds per persona, TUNABLE, **default 3** (was 5); needs N≥2 for SD/ICC to exist.
- Per persona: `can_exist` → fraction of N rounds = possibility probability p_i; `typicality` →
  mean_i ± SD_i; per-clash detection frequency (5/5 robust vs 2/5 marginal).
- Per combination: impossibility rate = mean(1−p_i) with bootstrap CI over personas; typicality
  **dispersion** over can_exist personas; clash taxonomy (which attribute pairs dominate).
- Two non-obvious points for defensibility:
  (a) **dispersion comparison ≠ mean comparison** — needs a variance test (Levene/Brown–Forsythe)
      or bootstrap CI on the dispersion metric, not a t-test on means.
  (b) **judge reliability metric** — use the 5 rounds to report ICC / Krippendorff's α as QC
      ("the judge is reliable"), before trusting the scores. Precedent: `method_significance/`
      already uses mixed-models / Friedman–Nemenyi.

## Judge model selection (research done 2026-07-23)
- **Self-preference bias is the decisive lever** (Panickssery et al., NeurIPS 2024, strong): a judge
  inflates its OWN family's generations, effect ∝ self-recognition. Personas here are generated by
  claude_sonnet + gemini + OpenRouter models → a Claude judge would inflate Claude combos, corrupting
  the exact method comparison that is the point. Aligned with the independent variable = severe.
  - Route A: single judge from a family that generated NONE of the compared personas (hard to
    guarantee if generators span Anthropic+Google+OpenRouter).
  - Route B (literature-endorsed): **judge panel ≥2 families**, aggregate (median/majority), and
    TEST a generator-family × judge-family interaction (reuse `method_significance/` mixed-model).
  - **DECISION (2026-07-23): defer the bias question — single judge for v1, run first & iterate.**
    Rationale (user): personas are mapped to a standardized JSON schema + canonical value vocab, so
    the stylistic self-recognition channel is destroyed (byte-identical tuples across generators).
    Caveat kept on record: the *shared-prior* channel (judge favoring value-combinations it would
    itself generate) survives standardization — watch for it if a pilot shows same-family combos
    scoring suspiciously high. Family constraint dropped → pick judge on capability. v1 default:
    Claude Sonnet (coherence axis) unless numeric axis is weighted higher (→ GPT-4o-class).
  - Raw capability (secondary): Claude Sonnet best on coherence/consistency; GPT-4o-class most robust
    numeric scorer (best for typicality). Small open judges (≤8B) OUT (number-fixation).
- **Corrections forced on the design:**
  - Temperature **0–0.1 (cold)**, NOT moderate. Reproducibility ~95%+ cold vs ~70% at T=1.
  - N-round agreement = **reliability, not validity** (self-agreement worst-case for frontier
    models). ICC/α proves stability, not correctness. → ADD: validate `can_exist` on a subset
    against **hard deterministic rules** (work_exp ≤ age−legal_working_age, etc.) = rules-vs-LLM check.
- **Confirmed right, now evidence-backed:** ordinal 0–10 integers (not continuous); constraint
  scaffolding in the prompt is the sweet spot (NOT a contradiction of "no rulebook" — it scaffolds
  constraint *categories* + "unusual≠impossible", not an enumerated pair-checklist).
- **New cheap additions:** anchored exemplars in typicality prompt ("rater training", cuts central-
  tendency clumping every model shows); subgroup-fairness audit of judge outputs (judge's own
  demographic priors may mark minority/immigrant profiles "atypical" → bias masquerading as a method
  difference).
- Reading list saved: JudgeBench (2410.12784), MT-Bench (2306.05685), Panickssery (self-preference),
  Reliability-without-Validity (2606.19544), Rating Roulette (EMNLP2025), Scoring Bias (2506.22316),
  Temperature (2603.28304), Verbalized Sampling/typicality (2510.01171).

## Judge invocation (decided 2026-07-23)
- **Judge model selectable via a config-driven dropdown; Claude models only; DEFAULT = Fable
  (`claude-fable-5`).** Fable is untested for data *generation* here but used as the *judge*.
  Dropdown options: claude-fable-5 (default), claude-opus-4-8, claude-sonnet-5, claude-haiku-4-5.
  List lives in CONFIG (not hardcoded), matching axis-composition model mapping.
- **Invoked through the SAME `claude` CLI provider the project already uses** (`--provider claude`,
  CLI on PATH — NOT the Anthropic API SDK). Headless call shape:
  `claude -p "<prompt>" --model claude-fable-5 --output-format json --append-system-prompt "<sys>"`
  - `--model <id>` = the single flag the dropdown value threads into.
  - `--output-format json` returns an ENVELOPE; envelope `.result` is the judge's JSON string →
    **double-parse** (envelope, then the can_exist/typicality/issues JSON inside `result`).
  - Fable availability is account/plan-dependent — smoke-test `claude -p "ping" --model
    claude-fable-5 --output-format json` before wiring; else it falls back to the default tier.
- **Wiring point (mapped):** all CLI invocation is in `src/population_synthetic/clients/
  claude_code_client.py` (`ClaudeCodeClient`). `--model` is ALREADY threaded (emitted line ~131,
  fed by per-call `model=` override line ~295 / constructor default `"sonnet"`). **No client change
  needed** — instantiate `ClaudeCodeClient(model_name="claude-fable-5")` or pass `model=` per call.
- **Corrections to earlier CLI notes** (this codebase's real invocation):
  - NOT `-p` one-shot — a persistent process speaking **NDJSON over stdin** (`--input-format
    stream-json` / `--output-format stream-json`, `--max-turns 1`).
  - **No double-parse:** the client already extracts the `result` string → parse the judge's JSON
    ONCE.
  - System prompt is `--system-prompt` (already wired), not `--append-system-prompt`.
- **Model dropdown = existing config pattern.** Generation model axes live in
  `config/synthetic/axes/models/*.yaml` (`claude_sonnet/opus/haiku`, each `provider: claude` +
  `model: <alias>`). Existing ones use SHORT aliases (sonnet/opus/haiku) → smoke-test whether Fable
  wants `"fable"` (alias) or `"claude-fable-5"` (full ID) as the `model:` value.
  - DESIGN DISTINCTION: those YAMLs are *generation* axes; the judge is an *analysis* task, so its
    model dropdown belongs in the ANALYSIS task config (default Fable), reusing `ClaudeCodeClient` —
    same YAML shape as a template, different home. Not a new generation axis.
- **Tool-lockdown caveat (fine for us):** CLI provider hard-locks `--disallowedTools` + `--max-turns
  1`. Correct for a pure-text judge verdict (judge needs no tools) — no change needed.

## Open questions
- Measurement primitive: pointwise vs pairwise vs reference-anchored?
- What dimensions does the judge score (coherence / plausibility / specificity)?
- How is SCB fed to the judge as a competitor without leaking its ground-truth status?
- Which judge model, and how to guard against self-preference bias?

## Remaining micro-threads (settle during planning)
- Typicality anchor exemplars (worked 1 / 5 / 9) — steer the scale; evidence backs anchoring.
- Tuple rendering: raw `axis: value` lines vs natural-language framing.
- Registry plumbing: canonical id (= registry key = GUI task key = `03_Analysis/<id>/` folder),
  subpackage `analysis/<id>/`, script, dispatch entry in `config/analysis/analysis_registry.yaml`.

## Session log
- 2026-07-23: Scoped the task down from the 3-branch umbrella to the individual-quality judge only;
  established the distribution-vs-coherence decoupling as the north star. Settled measurement
  primitive (pointwise coherence-flagging, not pairwise), the two-dimensional schema (can_exist +
  typicality), N-round aggregation + dispersion-vs-SCB stats + reliability QC, judge-model research
  (self-preference deferred, Fable default via existing claude CLI), and confirmed the CLI plumbing
  needs no client change. Status → Matured.
