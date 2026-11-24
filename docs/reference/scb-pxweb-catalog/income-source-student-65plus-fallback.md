# Income source for students aged 65 and over (declared fallback)

Status: implemented in the reference-v3 worktree, November 2026.

## Gap

The income-source table (`HE/HE0110/HE0110F/TabVX13InkStruktN`, components from
`HE0110A/SamForvInk1a`) has cells for the employment category "students" only for the
income age bands 20-29, 30-49 and 50-64. It has none for 65-79 and 80-.

The employment-status distribution that the sampler draws from decides whether an
individual can reach that gap:

- With the status-by-education merge ON (`ArbStatusUtbM`) nobody aged 65 or over becomes a
  student, so the gap is never hit.
- With the merge OFF (`--no-merge-status-education`, the single register table
  `ArRegArbStatus`) students aged 65 to 85 have probability 0.09 to 0.14% per (age group,
  sex) cell, about 2.7 of 10,000 individuals aged 18 to 85 in expectation (5 in the seed-42
  redraw). The sampler used to stop with `ValueError: No income_source distribution for
  cell (employment='students', age_group='65-74')` (and `'75-85'`).

## Rule

`SampleService` carries an explicit table, `_INCOME_SOURCE_AGE_FALLBACK`:

| income category | pipeline age group | borrows the mix of |
|---|---|---|
| students | 65-74 | 55-64 (income band 50-64) |
| students | 75-85 | 55-64 (income band 50-64) |

The fallback is applied only when the table has no cell for the individual's own age
group and only for the listed pairs. Every other missing cell still raises, as does a
fallback whose source cell is missing. It is an assumption, not an SCB figure: the student
mix at 55-64 is a stand-in for a group SCB does not report separately.

## Unemployed aged 80 and over

The same table has no "unemployed" cell for band 80- (ages 75-85). The merge-OFF
employment distribution gives "Unemployed" probability exactly 0.0 at 65-74 and 75-85 for
both sexes, so the generator never draws that cell and no entry is needed. If a future SCB
vintage makes that probability positive, the sampler raises again (fail-fast) and the pair
must be added here with its own decision.

## Tests

`tests/test_sweden_sampler.py`: students aged 65 to 85 use the 55-64 mix; a delivered
cell is never overridden; the rule does not extend to other ages or other statuses; a
missing source cell raises.
