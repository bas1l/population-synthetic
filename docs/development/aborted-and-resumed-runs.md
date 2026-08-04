# Aborted and resumed runs

How persona generation survives being killed, and what happens on the next run. Read this before
changing anything under `src/population_synthetic/generators/synthetic/`, and before adding a flag
that sounds like `--resume`.

---

## The premise

**The process can die at any instruction.** The GUI's Abort issues `taskkill /F /T`
(`gui/execution.py`), a laptop loses power, a container is recreated mid-sweep. Nothing in this
design assumes an orderly shutdown, and nothing may be added that does.

That premise has one direct consequence worth stating up front: **there is deliberately no signal
handler and no graceful drain.** It was considered and rejected. A `SIGINT` handler cannot help
against `taskkill /F` or a power cut — the exact cases in question — so it would only add a second,
weaker recovery path beside the kill-safe one, which then has to be kept correct without ever being
the path that actually runs. The right amount of shutdown logic here is none.

---

## What is on disk, and what each file means

Every persona owns exactly three files, and one object — `PersonaWriter` — owns all three.

| File | Meaning |
|------|---------|
| `identity.json` | The finished persona. Flat, single-level, and the run's **complete-output marker**. |
| `identity.partial.json` | The checkpoint: the categories resolved so far, in resolution order, plus the run's fingerprint and the correlation counter. Present **only** while the persona is unfinished. |
| `llm_interactions.jsonl` | One record per LLM *attempt*, keyed `(persona_id, call_index)`. |

Every durable write goes through `utils/atomic_io.py`: serialise into a `mkstemp` temp file in the
target's own directory, `flush`, `fsync`, then `os.replace`. A reader therefore only ever sees the
previous complete file or the new complete file — never a half-written one. That ordering is
load-bearing and must never be rearranged; replacing before `fsync` publishes a name that survives a
power cut while its contents do not.

---

## The three definitions everything rests on

**Complete persona (generation-side).** `identity.json` parses as JSON, is a **flat** object, and
carries a non-empty value for every category in this run's resolved category order.

This is deliberately a *different* predicate from `validate_raw`'s, which derives its expected keys
from the country's mapping `_index.json`. They are safe to keep separate because
`_assert_strategy_covers_country` already guarantees **strategy categories ⊇ country required keys**,
so a persona complete under the generation predicate is necessarily complete under `validate_raw`'s.
Generation's gate is the stricter of the two. Do not "unify" them without re-establishing that
containment — and note that doing so would also invert the layer dependency, since generation would
then import from the downstream analysis half.

It replaced an exists-only check (`if not force and out_file.exists()`), which could not tell a
finished persona from the truncated remains of a killed `json.dump` and so skipped the corrupt one
*forever*.

**Valid checkpoint.** `identity.partial.json` parses, its `schema_version` matches this build, and
its `fingerprint` block equals the current run's. Anything else — unparseable, torn, wrong version,
mismatched fingerprint — is *discarded*, not repaired, and logged at WARNING. Parse failure and
fingerprint mismatch are different facts and get different messages: one means the process died
mid-write, the other means the configuration moved under a healthy file.

The fingerprint is `{strategy_sha256, schema_sha256, model_key, category_order}`, the two hashes
over raw file bytes. A semantically inert reformat therefore invalidates checkpoints — the safe
direction to err in, because a discarded checkpoint costs LLM calls while a wrongly accepted one
splices two generation regimes into one persona that no experimental arm actually produced.

**Resume-faithful.** Category K's rendered prompt after a resume is byte-identical to the prompt an
uninterrupted run would have produced. It holds because the context block is a pure function of the
resolved dict's *contents and insertion order*, and the checkpoint restores both — the prefix is
replayed in DAG order and the checkpoint is never written with `sort_keys`. The resume walk stops at
the **first gap** rather than cherry-picking, so no category can see a context an uninterrupted run
would not have shown it.

Resume-faithful is **not** determinism. Generation is unseeded (`np.random.*`, `random.choices`), so
two runs of the same config already differ. Resume does not make that worse and does not checkpoint
RNG state — but nobody should later assume resume guarantees bit-identical output.

---

## The shared lifecycle invariant

> `llm_interactions.jsonl` is truncated **if and only if** the checkpoint is discarded.

* **resumed** → the JSONL opens in append mode *and* `call_index` continues past every index already
  spent;
* **fresh / `--force`** → the JSONL is truncated *and* `call_index` restarts at 0.

This is what keeps `(persona_id, call_index)` unique without asking any downstream consumer to
dedupe — and `generation_metadata` sums records *without* deduping, so a violation silently inflates
reported cost, retry counts and latency percentiles.

The two decisions can never disagree because both derive from one memoised verdict:
`PersonaWriter.telemetry` resolves `resume()` itself before opening the handle, so there is no call
order in which the append/truncate mode is fixed before the checkpoint was inspected.

**"Already spent" is not just the checkpoint's counter.** A category that exhausts its retry budget
records one telemetry entry per attempt and *then* raises, so the last checkpoint is older than the
highest index actually issued. The resume therefore continues past the larger of the checkpoint's
counter and the highest `call_index` the log itself carries. The log is read leniently — a killed
process can leave a torn trailing line, and one unparseable record must not cost the indices the
readable ones establish.

---

## Ordering constraints

Five, each commented at its site in the code. They are connascence of execution order — invisible to
a type checker and expensive to rediscover.

1. `write` → `flush` → `fsync` → `os.replace`. Never reorder.
2. Temp filenames are per-worker unique (`mkstemp` in the target dir), never a predictable
   `<name>.tmp` — the runner is parallel and two workers on one guessable name would interleave
   their bytes into one file.
3. `checkpoint()` is written **after** the category's value is in the resolved dict, never before. A
   checkpoint written first claims a category the run has not paid for, and the resumed persona
   carries a hole.
4. `finalize()` writes `identity.json` **before** unlinking the partial. A kill between the two
   leaves both files; the next run's gate sees a valid identity, skips the slot, and collects the
   orphan. The reverse order leaves a window in which neither file describes the persona.
5. `resume()` fixes the telemetry append/truncate mode **before** the first `record()`. Structural
   rather than conventional — see above.

---

## What a re-run actually does

`SyntheticPopulation.plan()` runs once, sequentially, at the orchestration edge — before the thread
pool exists — and partitions `range(n)`:

| Bucket | Meaning |
|--------|---------|
| `complete` | Finished personas. Skipped; a stale partial beside one is collected here and nowhere else. |
| `checkpointed` | Pending slots carrying a checkpoint file. They will re-pay for at most one category. |
| `pending` | Everything the run must fill. |

Doing it once, up front, buys three things: the verdict is one consistent snapshot that goes into
`run_metadata.json`; a fully-complete re-run starts no thread and constructs no LLM client at all;
and no worker can reach a different conclusion than the queue it was scheduled from.

`run_metadata.json` records it:

```json
"resume": {
  "resumed": true,
  "skipped_complete": 120,
  "resumed_from_checkpoint": 7,
  "pending": 80
}
```

A resumed run and a clean one are otherwise indistinguishable after the fact, and they are **not**
interchangeable: a resumed combo's wall-clock and token totals cover only the slots that invocation
actually paid for, so pooling them with a clean run's under-reports the population's true cost.
`--force` reports `resumed: false` by construction — it inherits nothing.

---

## `--force` is the only escape hatch

**There is no `--resume` flag, and none may be added.** `force-processing-analysis-tasks.md`
established force as batch-wide rather than per-unit and warned against new resume-flag vocabulary;
resuming is the *default*, so a flag to request it would be a flag to request normal behaviour.

The one distinction that does exist is internal, between two things the old fused `force` flag
conflated:

| | Re-enter a slot with no finished identity | Discard its checkpoint |
|-|-------------------------------------------|------------------------|
| **retry round** | yes | **no** — the categories the failed attempt paid for are still valid under the same fingerprint |
| **`--force`** | yes | yes |

`ensure-n-generation.md` originally chose `force=True` on every retry round "to ensure regeneration
regardless of any partial artifacts". This reverses that for the checkpoint specifically: a retry
round used to throw away exactly the work it was retrying.

Under `--force`, checkpoints are discarded by the writer each worker asks for — *not* during
planning. A run that died between planning and generating has therefore not already thrown the work
away.

---

## Operational notes

* **Recovering by hand.** Deleting every `**/identity.partial.json` returns a run directory to its
  pre-checkpoint state with no loss of completed personas. Deleting a persona's whole directory makes
  the next run regenerate that slot from scratch.
* **A persona that failed every retry round** leaves a partial and no `identity.json`.
  `validate_raw` classifies it as failed (no identity file) — which is correct: it is an unfinished
  slot, not a corrupt one.
* **The capped mirror is unaffected.** `population_cap` copies persona directories wholesale, and a
  complete persona has no partial to copy — a second, independent reason the checkpoint is deleted
  rather than retained.
* **Telemetry totals shifted upward** when this landed. That is a *correction*: the previous
  behaviour discarded a failed attempt's records on every retry round, so historical cost figures
  under-count actual spend. Do not compare token totals across the change without saying so.
* **Windows.** `os.replace` can raise `PermissionError` when the destination is momentarily held
  open or delete-pending. `atomic_io` retries narrowly (only `PermissionError`, bounded, jittered,
  logged) so a genuine permission problem still surfaces instead of being ridden out silently.

---

## Sub-category resume is out of scope

Resuming *within* a category — after `enumerate`, before `evaluate` — would require persisting the
`candidates`/`weights` locals. Not attempted. The unit of recovery is one category, and the worst
case a kill costs is one category's LLM calls.
