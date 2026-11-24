# Brainstorm: What the article should show about persona clashes

**Started:** 2026-09-22   **Last matured:** 2026-09-22   **Status:** Brainstorming

## Real goal (north star)
Decide what the paper needs to *claim* about the judge's clashes (severity S1/S2/S3 and the
attribute pairs behind them), so that any clash figure carries those claims and nothing else --
instead of plotting every count the pipeline produces.

## Where it stands
Clash rates are read **against the real population's rate, not against zero**. The same judge
flags the 100 real SCB individuals at S1 in 69 % of cases and at S2 in 11 %, against ~32 % S1
for synthetic individuals pooled; it flags none of them at S3. For S1 and S2 the target is
therefore to match the Reference -- fewer flags than real people is a miss ("too average"), not
a success. S3 stays a one-sided defect (40 of 5,800 synthetic individuals, all in the
employment status / employment type / income source triad; "only under strategies A and E" does
NOT survive a correction for having picked that contrast after seeing the data, p = 0.098, and no
model effect exists). The statistically supported driver story is strategy E: serious (S2+)
clashes 8.1 % vs 0.7 % elsewhere, every E cell affected, strategy explains ~half the variation,
model is not significant. No pair is flagged significantly more in synthetic than in the
Reference; several are flagged significantly more in the Reference. The Reference
becomes the yardstick of the figure. Measurement of each model and strategy against it is
running (scratchpad `clash_vs_reference/`), mirroring the typicality closeness design (TV
similarity, Reference self-resampling baseline, model + strategy decomposition).

## Alternatives on the table
- Clashes as **defect detector** only: S3 in a sentence plus a supplementary table, no figure.
- Clashes as **realism calibration** (chosen direction): gap to the Reference per level.
- Clashes as **mechanism for practitioners**: which attribute pairs break under which strategy.

## Threads explored
- Kept: Reference as yardstick for S1/S2 -- chosen 2026-09-22.
- Parked: per-pair driver figures (P03 variants, P18/P20) until the claim is fixed.
- Kept (caveat): same value pair lands at different levels because the judge reads the whole
  profile (third attribute decides, e.g. income source); a minority is judge inconsistency.

## Open questions
- Judge fairness: partly answered (`driver_stats/`). Strategy changes how often a value pair is
  *produced* (11 of 26 pairs), almost never how often it is *flagged once present* (1 of 19).
  But some pairs are flagged 27-74 % in synthetic vs 0 % in the Reference although produced less
  often -- the flag depends on the rest of the profile.
- Denominator: 100 judged per combination (settled). Provenance defect found: in 29 cells, 7-40
  of the judged individuals are from an earlier cap draw, not the current one; flag rates match
  (OR 0.90, p = 0.34), but the verdict cache is not tied to the cap roster.
- The Reference is 100 individuals, the first 100 of the sample: how large a gap can it detect?
- Does "too tidy on clashes" coincide with "too average on typicality"?
- Is there room for a clash figure in the short realism section, or does it go to supplement?

## Session log
- 2026-09-22: Framed three roles for clashes; chose "measure against the real population's rate".
- 2026-09-22: "Trade-off" framing DROPPED (untested; E matches the Reference's rate with different,
  employment-contradiction content). Paper states three separate findings: (1) most combinations
  too tidy vs the Reference; (2) strategy E has the most rank-2+ clashes; (3) rank-3 clashes rare,
  no supported strategy/model effect -- but name the E models carrying rank 3 (Kimi K3 10,
  GPT-OSS 120B 9, Mistral Medium 3.5 2). Docx draft written (Methods 4.4.2, descriptive Results
  5.3, Discussion, author notes): figures_selection\captions\
  severity_worst_clash_by_model_strategy.methods-results-discussion-draft.docx.
- 2026-09-22: Reference-yardstick results in (`clash_vs_reference/`): 39 of 58 combinations flag
  significantly fewer individuals than the Reference (69 %); every strategy and model pooled is
  below; E is closest (-14 points any clash, indistinguishable at S2+) yet carries most S2/S3
  errors -> trade-off: realistic messiness and genuine errors arrive together. Clash gap tracks
  typicality (rho 0.80), partly built in (same judge call). Only Mistral Nemo x A exceeds on S3
  after Holm. P19 chosen as the severity figure and exported with article terms.
- 2026-09-22: Driver statistics in: strategy E is the only supported driver effect; S3-by-strategy
  and S3-by-model claims dropped; judged-roster provenance defect found.
