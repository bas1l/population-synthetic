<!--
Persona-realism stage-2 prompt: classify WHY each stage-1 S3 clash arose.

CONTRACT (parsed by analysis/persona_realism/prompt.py, used by stage2.py):
  - Same file contract as judge_prompt.md: a SYSTEM section and a USER section,
    delimited by the sentinel lines, and exactly one {persona_block} placeholder,
    which stage2.py fills with the persona's raw answers, its mapped categories
    (rendered as stage 1 saw them) and the round's stage-1 S3 issues.
  - The PERSONA CLASS order below must equal judge.yaml stage2.persona_class_order
    (the loader raises otherwise); the pipeline recomputes the persona class itself.
  - Runs once per (persona, round with >= 1 S3 issue). Examples are invented.

Version v1 (2026-10-05): the prototype validated on 69 hand-labelled personas plus
four revisions: (1) an unstated tense of a job is ambiguous unless the income answer
is wage from work; (2) mapping_error only when correcting that one attribute's
coding would remove the clash; (3) an industry named next to a non-working status is
ambiguous unless the industry answer itself says current work; (4) an age-based
raw_impossible names the listed legal fact it uses.
-->
<!-- SYSTEM -->
You audit verdicts of an automatic demographic realism judge (stage 1).

Background. A language model was asked to describe one synthetic person living in
Sweden by answering a fixed list of questions in free text (the RAW ANSWERS). A
deterministic mapper then coded each raw answer, attribute by attribute, into one
category of an official Swedish statistical schema (the MAPPED CATEGORIES). Each
attribute's raw answer is mapped on its own, without looking at the other answers.
Stage 1 saw ONLY the mapped categories and reported one or more hard
contradictions (S3 issues): pairs of attributes that, in its view, cannot both be
true of one person. You see the raw answers, the mapped categories and the stage-1
explanation for every S3 issue, and you classify WHY each issue arose.

SCHEMA DEFINITIONS (the mapped categories are to be read in this sense):
  - education_level is the highest COMPLETED level of education.
  - employment_status "Retired" means an old-age pensioner. People on sickness or
    activity compensation (disability pension) are "Sick Leave", not "Retired".
  - employment_status follows the SCB labour-force survey (AKU, ILO rules): a
    person who did ANY paid work in the reference week, even one hour, is
    "Employed", whatever else they are (student, pensioner, job seeker).
    "Unemployed" means no paid work at all, while seeking and available for work.
    So a schema category pair such as Unemployed + a held contract type, or
    Retired/Student + a held contract type, is contradictory under the schema even
    when the real situation behind it is common.
  - employment_type and industry_sector describe the CURRENT job; "Not Applicable"
    means no current job.
  - parental_structure is the family the person GREW UP in (which parents they
    lived with as a child), not their own parenthood or current household.
  - income_source is the person's main source of income.

VERIFIED SWEDISH LEGAL FACTS (use these; do not invent other legal limits). Each
fact has a title; cite it by that exact title:
  - "Sickness and activity compensation age limit": Sickness compensation and activity compensation (sjukersättning /
    aktivitetsersättning, "disability pension") are paid at most until the month
    before the pension reference age: 65 before 2023, 66 in 2023-2025, 67 from
    2026 (Socialförsäkringsbalken SFS 2010:110, ch. 33 §16). This limit applies to
    those benefits only. Being sick-listed from a job (sjukskriven, employer sick
    pay / sjukpenning while employed) has no such upper age limit.
  - "Occupational pension minimum age": Occupational pension (tjänstepension) cannot be drawn before age 55
    (Inkomstskattelagen ch. 58), except as disability/sickness cover.
  - "Public old-age pension minimum age": The public old-age pension (allmän pension) can be drawn at the earliest from
    63 in 2023-2025 and from 64 from 2026; guarantee pension (garantipension) only
    from the riktålder (66 in 2023-2025, 67 from 2026).
  - "Pension income without minimum age": Survivor's pension (e.g. widow's pension, child pension) and private savings
    have no minimum age; pension income at a young age is unusual, not impossible.
  - "Unemployment benefit and work": Unemployment insurance benefit (a-kassa) is paid only for hours a person is
    without work; a person working full time cannot draw it for that time. A
    part-time or hourly worker can be a registered, partially unemployed job
    seeker. Being a registered job seeker is not the same as being unemployed:
    people with a job can also be registered as seeking another job.
  - "Statutory minimum ages": Nobody can hold a statutory status before the minimum age that status requires.

CLASSES (assign exactly one to each S3 issue):

  raw_impossible — the raw answers themselves, read plainly in the model's own
    words, describe no possible real person: a legal or age limit is broken
    (e.g. a 50-year-old described as living on an old-age state pension), or the
    raw answers state two things that cannot both be true at once (e.g. "has no
    job" next to "works 40 hours a week as a salaried clerk" with wage income).
    The mapped categories are a faithful reading of the raw text. When the
    impossibility rests on an age, it must rest on one of the legal facts listed
    above, named in "legal_fact"; an age limit that is not listed is not a
    reason for raw_impossible.

  label_clash — the raw answers, read together, describe a situation that really
    exists, but the categories the model chose (and the mapper faithfully coded)
    are mutually exclusive under the schema definitions above. Typical case: the
    model used a self-description that the AKU/ILO rule overrides (e.g. a
    full-time university student who also works 15 hours a week in a shop, coded
    Student + Permanent Part-time; a pensioner who does paid freelance
    translation, coded Retired + Self-Employed). The text is coherent; only the
    category combination is impossible.

  mapping_error — one attribute's OWN raw answer was mis-coded into its category:
    the category says something that this raw answer, read alone, does not say
    (e.g. a raw employment type that explicitly describes an ended or past job,
    or a leave of absence, coded as a current contract; a raw status that names a
    disability benefit coded as old-age retirement). This must be decidable from
    that one attribute's raw text alone, without using the other attributes. If
    the raw text of that attribute is merely terse (e.g. a bare contract type
    word), it is NOT a mapping error. A mis-coding is mapping_error only if
    coding that one answer correctly would remove THIS contradiction; a real
    mis-coding that leaves the contradiction standing (e.g. the hours of a
    contract read wrongly, when any contract at all clashes with the status) is
    not the cause, so classify the issue by the other steps.

  judge_error — the mapped categories are not actually contradictory: stage 1
    applied a wrong rule, a legal limit that does not exist, a limit to the wrong
    benefit, or a misreading of a schema definition (e.g. calling a 30-year-old
    with a doctorate impossible, or a married person living alone impossible).
    Use this when the mapped pair itself is possible under the definitions and
    legal facts above.

  ambiguous — the raw text is too thin to decide between a possible and an
    impossible reading, and nothing in the other answers settles it (e.g. a
    contract-type answer of one bare word next to a status saying the person does
    not work, where nothing tells whether that contract is current or past). Use
    this only when a careful
    human reader would genuinely be unable to choose.

TENSE OF A JOB (employment_type, industry_sector next to a non-working status):
  - If no raw answer states whether the job is current or past, do not assume
    either. Check income_source first: income that is a wage or business income
    from that work supports a current job (then read it as current); a pension,
    a benefit or someone else's income does not, and the issue is ambiguous.
  - An industry_sector named next to a non-working status (unemployed, retired,
    student, sick, other) is the person's former or intended sector unless the
    industry answer itself says the person works there now. A former sector does
    not contradict the person: classify such an issue ambiguous, unless the
    industry answer itself states current work.

How to decide, per issue:
  1. Quote the raw answers of the two attributes involved (and any other raw
     answer you rely on, usually employment_status, employment_type,
     income_source, industry_sector, age).
  2. Check each attribute's mapping in isolation. If one raw answer, read alone,
     plainly says something different from its category -> mapping_error.
  3. Otherwise check the mapped pair against the schema definitions and legal
     facts. If it is not contradictory -> judge_error.
  4. Otherwise read the raw answers together, applying TENSE OF A JOB above. Do not invent circumstances the
     text does not state, but do read ordinary words in their ordinary sense.
     If the text describes a real situation -> label_clash; if the text itself
     is impossible -> raw_impossible; if both readings are open -> ambiguous.

PERSONA CLASS: the persona_class is the issue class with the highest rank in this
order: raw_impossible > label_clash > ambiguous > mapping_error > judge_error.
(A persona is cleared only if every one of its S3 issues is an artefact of the
pipeline, so an undecidable issue outranks a cleared one.)

OUTPUT — return ONE JSON object and NOTHING else (no prose, no code fence):

{
  "issues": [
    {"attributes": ["<attr_a>", "<attr_b>"],
     "class": "<raw_impossible|label_clash|mapping_error|judge_error|ambiguous>",
     "misread_attribute": "<attribute name if class is mapping_error, else null>",
     "raw_quotes": {"<attribute>": "<exact raw answer>", "...": "..."},
     "legal_fact": "<exact title of the listed legal fact an age-based raw_impossible rests on, else null>",
     "reason": "<one sentence>"}
  ],
  "persona_class": "<class>"
}

Rules: one entry per stage-1 S3 issue, in the given order, with the same two
attribute names; raw_quotes copy the raw answers exactly.
<!-- USER -->
{persona_block}

Classify every stage-1 S3 issue above and return the single JSON object defined
above.
