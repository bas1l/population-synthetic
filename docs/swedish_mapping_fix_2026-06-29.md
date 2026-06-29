# Swedish Mapping-Gap Fix — Triage Record

*2026-06-29. Harvest → triage → fix → verify pass per
`docs/mapping_gap_investigation_playbook.md`. Companion to the prior
`swedish_mapping_fix_2026-05-29.md` and the state analysis in
`swedish_model_state_and_mapping_2026-06-29.md`.*

## Scope of this pass

Harvested the real unmapped values across **42 `swedish_*` runs / 3834 personas**
(`scripts/_throwaway_harvest_unmapped.py --country swedish`) and triaged the five
scored target fields. Going in, the structural failure modes from playbook §0 were
already closed: `employment_type` collapses to `Non-standard label` via
`_EMPLOYMENT_TYPE_OUTPUT` (extractor.py:1897), `civil_status` via
`_CIVIL_STATUS_OUTPUT` (1741), and `housing_tenure` appends to `unmapped` (1802).
So the only mechanism in play was JSON aliases (lowest-risk, pure data) — no code
changes to `extractor.py`.

**Headline finding:** the genuine mapping gaps were already closed by the prior
campaigns. The remaining unmapped residual is dominated by **field-misuse and
noise**, not by real categories the schema is missing (see "Left unmapped" below).

## Mapped (genuine categories → canonical target)

All added to `config/assets/scb_reference/category_mappings.json`
`pipeline_label_mappings`; each mirrors an existing entry, so it is a label
*translation*, never a class guess.

| Field | Alias added | → Target | Occurrences | Mirrors existing |
|---|---|---|---|---|
| socioeconomic | `high` | Wealthy | ~3 | `Hög` → Wealthy |
| socioeconomic | `upper` | Wealthy | ~2 | `Överklass` → Wealthy |
| parental_structure | `En förälder` | Single Parent | 2 | `Ensamförälder` → Single Parent |
| employment_type | `Obegränsad anställning` | Permanent Full-time | 4 | `Tillsvidareanställning` → Permanent Full-time (open-ended) |
| employment_type | `Tillfällig anställd` | Temporary Full-time | 2 | `Tillfälligt anställd` → Temporary Full-time |

Total: ~13 occurrences resolved. (`high`/`upper` are bare magnitude words; added
as **exact** JSON keys so they cannot substring-collide with `Hög utbildning`
(education leaking into class) or `Upper-middle class` → verified post-fix.)

## Left unmapped (deliberately — the noise floor)

- **`employment_type` field-misuse (dominant).** Hundreds of occurrences are
  **occupation titles**, not contract types: `Software Developer` (86 incl.
  casing), `studentjobb`/`studiejobb` (~40), `Student Assistant` (~27),
  `Projektledare` (9), `Lärare` (7), plus generic sector/role descriptors
  (`Private/Public sector employee`, `Employee`, `Salaried employee`). These give
  no permanence×hours signal and cannot map without fabricating one. **This is a
  generation-prompt / model-behaviour issue (playbook §6), not a mapping gap** —
  the remedy is a tighter prompt or a constrained (enumerated) config, not more
  aliases.
- **`civil_status` hallucination cluster.** `samarbeta`/`samarbete`/`samarbetaende`
  (~21) — "collaborate", a wrong word the model substitutes; explicitly noise per
  playbook §3. Left unmapped (and verified it *remains* unmapped post-fix).
  `Samtida`/`samtida` ("contemporary"), `Kärnfamilj` (parental label in the wrong
  field) likewise left.
- **`housing_tenure` category confusion / ambiguity.** `Egen hemförsäkring` (16) =
  home *insurance*, not a tenure (§3 noise). `föräldrahem`, `lägenhet` (apartment),
  `Living with family/relatives` — ambiguous as to tenure. Foreign/garbled
  ownership words (`Eigendom`, `Eigen`) left as language-confusion noise.
- **`socioeconomic_class` ambiguous tokens.** `Löntagare` (wage-earner),
  `Arbetslös`/`Arbetssökande`, `C1`/`C2` (NRS grades), `Pensionsränta` (income
  source), `Hög utbildning` (education) — none resolves to one of the four classes
  without guessing.
- **Long tail (freq-1):** hallucinations/garbles (`Tiohjuling`, `börmane`,
  `Enhetstablett familj`, …) — per §3, ignored.

## Verification (all gates passed)

1. **Re-harvest:** target occurrences fell exactly as predicted — socioeconomic
   175→170 (−5), employment_type 735→729 (−6), parental_structure 210→208 (−2);
   **`housing_tenure` 238→238 and `civil_status` 113→113 unchanged** — i.e. the
   `samarbeta` / `Egen hemförsäkring` noise correctly survives (proof nothing was
   force-mapped).
2. **No-regression:** `compare_pipeline_to_scb.py --model-id claude_haiku
   --strategy-id all_pick` — the clean run contains **0 collisions** with any of
   the 5 new alias keys, so its marginals/TV are unchanged by construction
   (add-only aliases can only convert a former `Non-standard label` into a
   category, never alter an already-resolved value).
3. **Lint:** `ruff check extractor.py` shows the same single pre-existing E501 as
   `git show HEAD:…extractor.py | ruff check -` — no new errors (extractor.py was
   not edited).
4. **Regenerated** all 42 Swedish reports + charts via
   `compare_all_pipelines.py --country swedish`.
