# How to replicate the SCB PxWeb catalog search + report

A two-step, dependency-free pipeline (Python stdlib only) that walks the SCB PxWeb API,
dumps every table's metadata, and renders a searchable HTML report. Use it to answer
"does SCB have a table filtered by X (and Y)?" for any subject area — not just labour/education.

## The idea in three sentences

1. The PxWeb API is a **tree**: `GET .../ssd/{path}` returns either a list of child nodes
   (each typed `"l"` folder or `"t"` table) or, for a full table path, that table's **metadata**.
2. A table's metadata lists its **variables** (dimensions) — each with a `code` (e.g. `Alder`,
   `UtbildningsNiva`, `ContentsCode`), a `text`, and its `values`/`valueTexts`.
3. So: walk the tree collecting every `"t"`, fetch each one's metadata, and a table "supports
   filtering by X" iff a variable with the right code / value-labels is present.

Base endpoint (English labels): `https://api.scb.se/OV0104/v1/doris/en/ssd`
(swap `/en/` → `/sv/` for Swedish labels).

## Step 1 — Dump metadata → JSONL

```bash
python scb_dump.py            # writes scb_full_metadata.jsonl (one table per line)
```

`scb_dump.py`:
- Walks the subtrees in `ROOTS` (default `["AM", "UF"]` — change these to sweep other areas,
  e.g. `["BE"]` for population, `["HE"]` for income).
- Throttles at `DELAY = 0.35 s` between calls to respect SCB's **~30 requests / 10 s** limit;
  retries `HTTP 429`, skips non-transient `4xx`.
- Emits, per table: `id`, `title`, and every variable's `code`, `text`, `elimination`/`time`
  flags, `n_values`, and full `values` + `valueTexts`.

Runtime: ~7 min for AM+UF (968 tables). Run it in the background.

## Step 2 — Build the HTML report

```bash
python build_report.py        # reads the JSONL, writes scb_report.html (self-contained)
```

`build_report.py` classifies each table from its metadata and renders a searchable page:
- **Attribute flags** are pure functions of the variables present. To search for a *different*
  capability, edit these near the top:
  - age → variable code `alder` / text containing `age`; `classify_age()` distinguishes a real
    breakdown (single-year / narrow bands) from a working-age **total** like `20–64`.
  - education → code contains `utbild` / text contains `education`.
  - status → code `Arbetskraftstillh`, **or** any value label in `STATUS_KEYS`
    (`unemploy`, `not in the labour force`, `labour force`, …).
- Value lists are capped at 50 per variable for display; the JSONL keeps everything.

Open `scb_report.html` in any browser — search runs over IDs, titles, and value labels; the
filter chips and summary cards narrow to tables with a given attribute.

## Adapting it to a new question

| You want | Do this |
|----------|---------|
| A different subject area | Change `ROOTS` in `scb_dump.py`, re-run both steps. |
| A different "capability" filter | Add a flag in `build_report.py` (mirror the `has_edu` / `has_status` pattern) keyed on a variable `code` or `valueTexts` keyword. |
| Just the data, no report | Query the JSONL directly, e.g. find tables with both age and education:<br>`jq 'select([.variables[].code] as $c \| ($c \| any(ascii_downcase=="alder")) and ($c \| any(test("utbild";"i"))))' scb-am-uf-metadata.jsonl` |
| The raw variables of one table | `GET https://api.scb.se/OV0104/v1/doris/en/ssd/AM/AM0401/AM0401A/AKURLBefAr` |

## Gotchas

- **Rate limit.** Keep `DELAY ≥ 0.34 s`. On `429`, back off — don't hammer.
- **En-dash vs hyphen.** Age labels use `–` (U+2013), not `-`; normalize before matching
  (`classify_age` does this) or "working-age total" tables get misread as real bands.
- **Windows console encoding.** Write output files with `encoding="utf-8"`; don't rely on
  `print` redirection (cp1252 corrupts `–`, `ä`, etc.). Set `PYTHONIOENCODING=utf-8` for stdout.
- **"Present" ≠ "cross-tabulable."** A variable listed in metadata can still collapse to a single
  aggregate once another dimension is selected (the `ArbStatusUtbM` age-`20–64` trap). Confirm a
  real cross-tab by issuing an actual POST query for the specific cell combination.
