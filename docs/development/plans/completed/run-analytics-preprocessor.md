# Plan: Run Analytics Preprocessor

**Date:** 2026-06-01
**Author:** Basil
**Status:** Completed
**Completed:** 2026-06-29 17:46
**Base Branch:** `dev`
**Branch:** `feature/run-analytics-preprocessor`

---

## Overview

Build a standalone preprocessing script `scripts/analyze_run.py` that parses the existing output files from identity generation runs (`llm_interactions.jsonl`, `logs/run_*.log`, `run_metadata.json`) and produces structured analytics. No changes to the generation pipeline — this is purely post-processing.

## Problem Statement

Identity generation runs already capture rich data across three output files: per-call interaction logs (JSONL), human-readable run logs with token/timing metrics, and run metadata JSON. However, the most valuable metrics — token consumption, inference latency, retry rates, value diversity — require manual inspection or ad-hoc regex parsing to extract. There is no structured way to answer questions like "how many tokens did this run consume?" or "which categories have the highest retry rate?" or "how does model A compare to model B on speed and reliability?"

The token counts and timing data (`prompt_tokens`, `completion_tokens`, `elapsed_ms`) are logged to the text log file as unstructured lines but are **not** present in the structured JSONL. The preprocessing script bridges this gap by joining both sources.

## Goals

### In Scope
1. Parse `llm_interactions.jsonl` (or `.json` array format) for per-call structured data
2. Regex-extract token counts and timing from `logs/run_*.log` lines
3. Join log-derived metrics to JSONL entries via timestamp proximity
4. Compute per-category, per-persona, and per-run aggregate metrics
5. Support single-persona directories and multi-persona batch directories
6. Console table output and optional `--output run_analytics.json` structured export

### Out of Scope
- Modifying the generation pipeline or `LLMInteractionEntry` dataclass
- Matplotlib charts or HTML dashboards (future enhancement)
- Cross-run comparison in a single invocation (run the script twice and compare the JSON outputs)
- Real-time / streaming analysis during a run

## Success Criteria

- [ ] `python scripts/analyze_run.py <output_dir>` parses a batch run directory and prints a summary table
- [ ] `python scripts/analyze_run.py <persona_dir>` parses a single-persona directory
- [ ] Token counts extracted from log files match the values visible in the log text
- [ ] `--output run_analytics.json` writes a structured JSON file with all computed metrics
- [ ] Works with both `.jsonl` (line-delimited) and `.json` (array) interaction file formats
- [ ] Works with Ollama, OpenAI-compat, and Claude log line formats
- [ ] Standard library only — no pandas, matplotlib, or other external dependencies

---

## Technical Design

### Approach

Three-layer parsing architecture:

1. **JSONL parser** — Reads `llm_interactions.jsonl` (or `.json`) files, yields `LLMInteractionEntry`-equivalent dicts. Handles both JSONL and JSON array formats transparently.

2. **Log parser** — Regex-extracts structured call lines from `logs/run_*.log`. Three patterns:
   - `(ollama|openai_compat) call: model=(\S+) base_url=(\S+) elapsed_ms=([\d.]+) prompt_tokens=(\S+) completion_tokens=(\S+)`
   - `claude call: model=(\S+) t_launch_ms=([\d.]+) t_inference_ms=([\d.]+)`
   - Run-level lines: `Done in (\d+\.\d+)s. Success: (\d+), Failed: (\d+)`

3. **Joiner** — Matches log entries to JSONL entries by timestamp proximity (within a tolerance window). Produces enriched records with both structured fields and token/timing metrics.

4. **Aggregator** — Computes analytics grouped by category, method, persona, and run. Outputs a summary dict.

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| Standalone script (stdlib only) | Zero dependencies; easy to run anywhere; simple | No charting; tables are text-only | **Chosen** |
| Pandas-based analysis notebook | Rich aggregation; pivot tables; easy charting | Adds dependency; heavier than needed for v1 | Deferred to v2 |
| Modify `LLMInteractionEntry` to include tokens | Cleanest — no log parsing needed | Violates constraint: no pipeline changes | Rejected |

### Architecture

```
scripts/analyze_run.py          # CLI entry point + output formatting
src/population_synth/analysis/
    __init__.py
    interaction_parser.py       # JSONL/JSON array parser
    log_parser.py               # Regex extraction from run log files
    joiner.py                   # Timestamp-based join of JSONL + log data
    aggregator.py               # Metric computation and grouping
```

### Analytics computed (v1 scope)

From JSONL alone:
- Per-category call count
- Retry rate by category and by method
- Error taxonomy (error type counts)
- Prompt size growth (len(prompt) by chain position)
- Response verbosity ratio (len(raw_response) vs len(json.dumps(parsed_value)))
- Generation method distribution
- Wall-clock time per persona (first to last timestamp)
- Value diversity / Shannon entropy per category (batch runs)

From log files (joined):
- Token consumption per persona (sum of prompt_tokens + completion_tokens)
- Token consumption per category
- Tokens-per-second inference throughput
- Latency distribution by category (median, p95, max)
- Token budget breakdown by step type (enumerate, evaluate, pick, retry)

---

## Implementation Plan

### Phase 1: Parsers
**Goal:** Reliable extraction from both data sources
**Started:** 2026-06-01
**Completed:** 2026-06-01

- [x] `interaction_parser.py` — Parse JSONL and JSON array formats; return list of dicts with all fields
- [x] `log_parser.py` — Regex extraction of call lines; return list of dicts with `{timestamp, provider, model, elapsed_ms, prompt_tokens, completion_tokens}`
- [x] Handle edge cases: missing fields, `None` token counts, Claude's different metric names (`t_launch_ms`, `t_inference_ms`)

**Files Created:**
- `src/population_synth/analysis/__init__.py`
- `src/population_synth/analysis/interaction_parser.py`
- `src/population_synth/analysis/log_parser.py`

**Dependencies:** None

### Phase 2: Join and Aggregate
**Goal:** Combine data sources and compute metrics
**Started:** 2026-06-01
**Completed:** 2026-06-01

- [x] `joiner.py` — Match log entries to JSONL entries by timestamp proximity (configurable tolerance, default 2s)
- [x] `aggregator.py` — Compute all v1 metrics; return a nested dict structure suitable for JSON export
- [x] Shannon entropy calculation for value diversity (stdlib `math.log2`)

**Files Created:**
- `src/population_synth/analysis/joiner.py`
- `src/population_synth/analysis/aggregator.py`

**Dependencies:** Phase 1

### Phase 3: CLI and Output
**Goal:** Usable script with console and JSON output
**Started:** 2026-06-01
**Completed:** 2026-06-01

- [x] `scripts/analyze_run.py` — CLI with argparse: `<run_dir>`, `--output`, `--verbose`
- [x] Auto-detect directory type (single persona vs. batch with `persona_*` subdirs)
- [x] Console table formatting for summary output
- [x] JSON export with `--output`

**Files Created:**
- `scripts/analyze_run.py`

**Dependencies:** Phase 2

---

## Testing Plan

### Manual Verification
- [ ] Run against `data/identity/config_004_n01_claude_test_llmlog/persona_00000/` (single persona, Claude provider)
- [ ] Run against root-level `llm_interactions.json` + `logs/` (single persona, Ollama provider)
- [ ] Verify extracted token counts match the values in the log file (spot-check 3-5 entries)
- [ ] Verify `--output` JSON is valid and contains all expected top-level keys
- [ ] Run against a batch output directory with multiple `persona_*` subdirs (when available)

### Edge Cases
- [ ] JSONL file with retry entries (`step` ending in `_retry`, `error` non-null)
- [ ] Log file with no token lines (e.g. Gemini provider which doesn't log tokens)
- [ ] Missing log file (JSONL-only analytics should still work)
- [ ] Mixed JSON array format (`.json`) vs. JSONL format (`.jsonl`)

---

## Documentation Plan

- [x] Update CLAUDE.md commands section with `analyze_run.py` usage
- [x] Add docstring to `scripts/analyze_run.py` with example output

---

## Rollback Plan

This is a purely additive feature — new files only, no modifications to existing code.

1. Delete `src/population_synth/analysis/` directory
2. Delete `scripts/analyze_run.py`

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Timestamp join mismatches (log line doesn't align to JSONL entry) | Medium | Medium | Use tolerance window; fall back to sequential ordering when timestamps are ambiguous |
| Log format changes in future client updates | Low | Medium | Regex patterns are isolated in `log_parser.py`; easy to update |
| Large batch runs (N=1000) produce slow analysis | Low | Low | All operations are single-pass streaming; no in-memory explosion |
| Older runs use `.json` array format instead of `.jsonl` | High | Low | Parser handles both formats transparently |

---

## References

- Research notes: `.claude/plans/the-generated-log-files-bubbly-stroustrup.md` (36 analytics ideas)
- Interaction logger: `src/population_synth/identity/llm_interaction_log.py`
- Client log lines: `src/population_synth/clients/ollama_client.py:208-216`, `openai_compat_client.py:208-216`, `claude_code_client.py:284-289`

## Modified Files

<!-- auto-generated by /plan-implement — do not edit manually -->
- CLAUDE.md
- docs/development/plans/active/run-analytics-preprocessor.md
- scripts/analyze_run.py
- src/population_synth/analysis/__init__.py
- src/population_synth/analysis/aggregator.py
- src/population_synth/analysis/interaction_parser.py
- src/population_synth/analysis/joiner.py
- src/population_synth/analysis/log_parser.py
