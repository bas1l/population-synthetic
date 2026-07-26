"""persona_realism -- LLM-as-judge individual-persona coherence analysis.

An analysis subpackage that judges each individual mapped persona (a bare
demographic tuple) with an LLM, N times at cold temperature, asking two
orthogonal questions per persona: can this attribute set describe one real
person (``can_exist``), and if so how typical is it (``typicality`` 0-10). The
process ranks every generation combination -- plus the SCB real population as one
more competitor -- on an impossibility rate and a typicality dispersion the
distributional pipeline cannot measure.

Four strictly one-way layers (pipe-and-filter; each depends only on the ones
above it, never downward):

    1. prompt.py  -- render a persona tuple + system prompt from the config
                     template. Pure; no stats, no disk except reading the
                     template. Produces ``(system_str, user_str)``.
    2. judge.py   -- one judge call -> one parsed, validated ``RoundVerdict``.
                     The SINGLE fail-loud normalization/validation boundary;
                     malformed or contract-violating judge JSON raises here.
    3. runner.py  -- resumable, parallel fan-out (N rounds x personas) that
                     writes, at the combo root, one ``persona_XXXXX.json``
                     verdict-cache file plus its sibling per-call
                     ``persona_XXXXX.jsonl`` telemetry (1:1) for the cost chain.
                     Resume is round-count-aware: re-running with a higher
                     ``--rounds`` tops up each persona (appending rounds), and a
                     persona is skipped only at ``>= n_rounds`` cached rounds. A
                     failed call is kept distinct from a possible verdict.
    4. reduce/stats/sinks (later phases) -- pure reduction round->persona->combo,
                     combo-level statistics, and the figure/CSV/JSON sinks.

The non-determinism (the LLM) is isolated in layer 2/3; everything downstream is
pure and depends only on the ``RoundVerdict``/``PersonaVerdict``/``ComboRealism``
DTO contracts. Config (``config/analysis/persona_realism/``) is the single source
of truth; missing/malformed config raises (fail-fast).
"""
