"""Tests for ``cost_efficiency/raw_cost.py`` -- cost over the full generated pool.

The distinctions under test are the ones that corrupt the downstream figure when
collapsed: a *measured* zero for an unmetered model against an *absent* cost for a
combination with no telemetry, and an absent pricing entry against either. The last
test is the live check that the whole module exists for -- the ``01_Raw`` total for a
combination that generated 549 personas to keep 100 must exceed the capped-mirror
total ``generation_metadata`` reports for it.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from population_synthetic.analysis.cost_efficiency.raw_cost import (
    COST_BASIS,
    RAW_STAGE_DIR,
    load_raw_pricing,
    pricing_document,
    raw_cost_for_slug,
)
from population_synthetic.analysis.utils.registry import analysis_output_dir, resolve_output_base
from population_synthetic.generators.synthetic.manifest_loader import axis_slug

# --- fixtures ---------------------------------------------------------------

PRICED_MODEL = "test_priced_model"
UNMETERED_MODEL = "test_unmetered_model"
UNPRICED_MODEL = "test_unpriced_model"

_PRICING_YAML = f"""\
observed_date: "2026-07-29"
source: "test snapshot"
currency: "USD_per_1M_tokens"

cache_multipliers:
  read: 0.1
  write: 1.25

models:
  # a comment line inside the block must not become a model row
  {PRICED_MODEL}:    {{in: 2.0, out: 10.0}}   # [VERIFY] [effective/discounted]
  {UNMETERED_MODEL}: {{in: 0, out: 0}}
"""


def _write_pricing(tmp_path: Path, text: str = _PRICING_YAML) -> Path:
    path = tmp_path / "model_pricing.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _write_persona(
    base: Path,
    slug: str,
    persona_id: str,
    records: list[dict],
    *,
    filename: str = "llm_interactions.jsonl",
) -> Path:
    """Write one persona dir with an interaction log under ``{base}/01_Raw/{slug}``."""
    persona_dir = base / RAW_STAGE_DIR / slug / persona_id
    persona_dir.mkdir(parents=True, exist_ok=True)
    path = persona_dir / filename
    if filename.endswith(".jsonl"):
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
        )
    else:
        path.write_text(json.dumps(records), encoding="utf-8")
    return persona_dir


def _call(persona_id: str, call_index: int, prompt: int | None, completion: int | None) -> dict:
    return {
        "category": "age",
        "attempt": 1,
        "persona_id": persona_id,
        "call_index": call_index,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": None if prompt is None or completion is None else prompt + completion,
    }


# --- pricing table ----------------------------------------------------------


def test_pricing_carries_provenance_and_inline_caveat_flags(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))

    assert pricing.provenance.observed_date == "2026-07-29"
    assert pricing.provenance.source == "test snapshot"
    assert pricing.provenance.currency == "USD_per_1M_tokens"
    assert pricing.provenance.config_path.endswith("model_pricing.yaml")
    # The caveat tags live only in the YAML comments, which safe_load discards.
    assert pricing.provenance.flags_for(PRICED_MODEL) == ("VERIFY", "effective/discounted")
    # An untagged row is an empty tuple -- a positive statement, not a missing key.
    assert pricing.provenance.flags_for(UNMETERED_MODEL) == ()


def test_pricing_document_is_restricted_sorted_and_states_unmetered(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    doc = pricing_document(pricing, [UNMETERED_MODEL, PRICED_MODEL, PRICED_MODEL])

    assert list(doc["models"]) == sorted([PRICED_MODEL, UNMETERED_MODEL])
    assert doc["cost_basis"] == COST_BASIS
    assert doc["models"][UNMETERED_MODEL]["unmetered"] is True
    assert doc["models"][PRICED_MODEL]["unmetered"] is False
    assert doc["models"][PRICED_MODEL]["flags"] == ["VERIFY", "effective/discounted"]
    # Deterministic: no timestamp, no set iteration order.
    assert doc == pricing_document(pricing, [PRICED_MODEL, UNMETERED_MODEL])


def test_missing_pricing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_raw_pricing(tmp_path / "nope.yaml")


def test_pricing_missing_top_level_key_raises(tmp_path: Path) -> None:
    path = _write_pricing(tmp_path, "source: x\ncurrency: y\nmodels:\n  m: {in: 1, out: 1}\n")
    with pytest.raises(ValueError, match="observed_date"):
        load_raw_pricing(path)


def test_the_shipped_pricing_config_loads(tmp_path: Path) -> None:
    """The real config must parse -- it is the one this process actually prices with."""
    pricing = load_raw_pricing()
    assert pricing.provenance.currency
    assert pricing.rates
    # The four local models in the live grid now carry a rented-equivalent rate
    # (what the same model costs to rent per token), so they are no longer
    # unmetered. The untouched, un-researched locals still are.
    assert pricing.is_unmetered("ollama_gemma4_e4b") is False
    assert pricing.is_unmetered("ollama_qwen3_14b") is True
    assert pricing.is_unmetered("openrouter_qwen35_flash") is False


# --- cost over the pool -----------------------------------------------------


def test_priced_model_totals_the_whole_pool(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [
        _call("persona_00000", 1, 1000, 500),
        _call("persona_00000", 2, 2000, 250),
    ])
    _write_persona(tmp_path, slug, "persona_00001", [_call("persona_00001", 1, 3000, 1250)])

    totals = raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    assert totals.n_personas == 2
    assert totals.n_personas_with_interactions == 2
    assert totals.n_personas_with_tokens == 2
    assert totals.n_calls == 3
    assert totals.n_unkeyed_calls == 0
    assert totals.input_tokens == 6000
    assert totals.output_tokens == 2000
    assert totals.has_token_data is True
    assert totals.unmetered is False
    assert totals.cost_basis == COST_BASIS
    assert totals.pricing_flags == ("VERIFY", "effective/discounted")
    # 6000 * 2.0/1e6 + 2000 * 10.0/1e6
    assert totals.total_cost_usd == pytest.approx(0.012 + 0.020)


def test_unmetered_model_is_a_measured_zero_never_absent(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + UNMETERED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [_call("persona_00000", 1, 4321, 8765)])

    totals = raw_cost_for_slug(tmp_path, slug, UNMETERED_MODEL, pricing)

    assert totals.unmetered is True
    assert totals.has_token_data is True
    assert totals.total_cost_usd is not None, "unmetered is a measured zero, not an absence"
    assert totals.total_cost_usd == pytest.approx(0.0)
    # The tokens are still reported -- unmetered is not free, it is unpriced-by-config.
    assert totals.input_tokens == 4321
    assert totals.output_tokens == 8765


def test_absent_pricing_entry_raises_and_names_the_model_and_config(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + UNPRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [_call("persona_00000", 1, 10, 10)])

    with pytest.raises(KeyError) as exc:
        raw_cost_for_slug(tmp_path, slug, UNPRICED_MODEL, pricing)

    message = str(exc.value)
    assert UNPRICED_MODEL in message
    assert "model_pricing.yaml" in message


def test_absent_pricing_raises_even_without_any_telemetry(tmp_path: Path) -> None:
    """Unpriceable is a config gap, so it must not be masked by thin telemetry."""
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + UNPRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [_call("persona_00000", 1, None, None)])

    with pytest.raises(KeyError, match=UNPRICED_MODEL):
        raw_cost_for_slug(tmp_path, slug, UNPRICED_MODEL, pricing)


def test_no_token_data_is_absent_not_zero(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [
        _call("persona_00000", 1, None, None),
        _call("persona_00000", 2, None, None),
    ])

    totals = raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    assert totals.has_token_data is False
    assert totals.total_cost_usd is None, "no telemetry is absent cost, never 0.0"
    assert totals.input_tokens is None
    assert totals.output_tokens is None
    assert totals.n_calls == 2
    assert totals.n_personas_with_tokens == 0
    # The pricing fact is independent of the telemetry fact.
    assert totals.unmetered is False


def test_unmetered_without_telemetry_is_still_absent(tmp_path: Path) -> None:
    """The two facts stay separable: unmetered pricing, absent measurement."""
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + UNMETERED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [_call("persona_00000", 1, None, None)])

    totals = raw_cost_for_slug(tmp_path, slug, UNMETERED_MODEL, pricing)

    assert totals.unmetered is True
    assert totals.has_token_data is False
    assert totals.total_cost_usd is None


def test_persona_without_an_interaction_log_is_counted_in_the_pool(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [_call("persona_00000", 1, 100, 100)])
    (tmp_path / RAW_STAGE_DIR / slug / "persona_00001").mkdir(parents=True)

    totals = raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    assert totals.n_personas == 2, "the generated pool is every persona dir on disk"
    assert totals.n_personas_with_interactions == 1


def test_duplicate_call_key_raises_naming_the_persona_and_file(tmp_path: Path) -> None:
    """The aborted-and-resumed double-counting guard."""
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00007", [
        _call("persona_00007", 1, 100, 100),
        _call("persona_00007", 2, 100, 100),
        _call("persona_00007", 1, 100, 100),
    ])

    with pytest.raises(ValueError) as exc:
        raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    message = str(exc.value)
    assert "persona_00007" in message
    assert "call_index=1" in message
    assert "llm_interactions.jsonl" in message


def test_duplicate_across_two_persona_files_raises(tmp_path: Path) -> None:
    """A mis-filed log collides on the record's own persona_id rather than hiding."""
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    _write_persona(tmp_path, slug, "persona_00000", [_call("persona_00000", 1, 10, 10)])
    _write_persona(tmp_path, slug, "persona_00001", [_call("persona_00000", 1, 10, 10)])

    with pytest.raises(ValueError, match="persona_00000"):
        raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)


def test_calls_without_a_call_index_are_counted_as_unkeyed(tmp_path: Path) -> None:
    """Legacy records cannot be deduped; the limit travels as a field, not a docstring."""
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    record = _call("persona_00000", 1, 100, 50)
    record["call_index"] = None
    record["persona_id"] = None
    _write_persona(tmp_path, slug, "persona_00000", [record, _call("persona_00000", 2, 100, 50)])

    totals = raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    assert totals.n_calls == 2
    assert totals.n_unkeyed_calls == 1
    assert totals.input_tokens == 200


def test_cache_tokens_are_priced_through_the_multipliers(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    record = _call("persona_00000", 1, 1000, 0)
    record["cache_read_tokens"] = 10_000
    record["cache_creation_tokens"] = 4_000
    _write_persona(tmp_path, slug, "persona_00000", [record])

    totals = raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    assert totals.cache_read_tokens == 10_000
    assert totals.cache_creation_tokens == 4_000
    expected = 1000 * 2.0 / 1e6 + 10_000 * 2.0 * 0.1 / 1e6 + 4_000 * 2.0 * 1.25 / 1e6
    assert totals.total_cost_usd == pytest.approx(expected)


def test_cache_tokens_without_a_multiplier_block_raise(tmp_path: Path) -> None:
    text = _PRICING_YAML.replace("cache_multipliers:\n  read: 0.1\n  write: 1.25\n", "")
    pricing = load_raw_pricing(_write_pricing(tmp_path, text))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    record = _call("persona_00000", 1, 1000, 0)
    record["cache_read_tokens"] = 500
    _write_persona(tmp_path, slug, "persona_00000", [record])

    with pytest.raises(ValueError, match="cache_multipliers"):
        raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)


def test_legacy_json_array_log_is_read(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    _write_persona(
        tmp_path,
        slug,
        "persona_00000",
        [_call("persona_00000", 1, 1000, 1000)],
        filename="llm_interactions.json",
    )

    totals = raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)

    assert totals.n_calls == 1
    assert totals.input_tokens == 1000


def test_non_integer_token_count_raises(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))
    slug = "swedish_02_all_pick_v2_" + PRICED_MODEL
    record = _call("persona_00000", 1, 100, 100)
    record["prompt_tokens"] = "100"
    _write_persona(tmp_path, slug, "persona_00000", [record])

    with pytest.raises(ValueError, match="prompt_tokens"):
        raw_cost_for_slug(tmp_path, slug, PRICED_MODEL, pricing)


def test_missing_raw_pool_raises_and_names_the_path(tmp_path: Path) -> None:
    pricing = load_raw_pricing(_write_pricing(tmp_path))

    with pytest.raises(FileNotFoundError, match="absent_slug"):
        raw_cost_for_slug(tmp_path, "absent_slug", PRICED_MODEL, pricing)


# --- the live 5.5x case (task 4.3) ------------------------------------------

_LIVE_COUNTRY = "swedish_02"
_LIVE_STRATEGY = "all_generate_evaluate_random_pick_v2"
_LIVE_MODEL = "openrouter_qwen35_flash"


def _capped_total_usd(summary_csv: Path, model: str, method: str) -> float:
    """``cost_mean * cost_n`` for one combination of the generation_metadata summary."""
    with open(summary_csv, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["model"] == model and row["method"] == method:
                return float(row["cost_mean"]) * int(row["cost_n"])
    raise AssertionError(f"{model} x {method} absent from {summary_csv}")


def test_raw_pool_cost_exceeds_the_capped_mirror_cost() -> None:
    """The reason this module exists: the capped mirror understates a wasteful run.

    ``generation_metadata`` measures cost over the ~100 selected personas; this
    combination generated 549 to keep them. Its ``01_Raw`` total must therefore be
    several times the capped total. Skipped rather than failed when the live output
    base or the upstream summary is not present.
    """
    output_base = resolve_output_base(None)
    slug = axis_slug(_LIVE_MODEL, _LIVE_STRATEGY, _LIVE_COUNTRY)
    if not (output_base / RAW_STAGE_DIR / slug).is_dir():
        pytest.skip(f"live raw pool not present: {output_base / RAW_STAGE_DIR / slug}")
    summary_csv = (
        analysis_output_dir("generation_metadata", output_base, for_read=True)
        / f"{_LIVE_COUNTRY}_summary.csv"
    )
    if not summary_csv.exists():
        pytest.skip(f"generation_metadata summary not present: {summary_csv}")

    pricing = load_raw_pricing()
    totals = raw_cost_for_slug(output_base, slug, _LIVE_MODEL, pricing)
    capped = _capped_total_usd(summary_csv, _LIVE_MODEL, _LIVE_STRATEGY)

    assert totals.has_token_data is True
    assert totals.total_cost_usd is not None
    assert totals.n_personas > 500, "the generated pool, not the capped 100"
    assert capped > 0
    assert totals.total_cost_usd > capped
    # The gap tracks the pool/cap ratio (549/100); anything near 1.0 would mean the
    # reader had silently landed on the capped mirror after all.
    assert totals.total_cost_usd / capped > 3.0


# ----------------------------------------------------------------------
# Calibrated exception path -- models priced from a comparable API because
# their own telemetry cannot be priced (see cost_calibration.json).
# ----------------------------------------------------------------------

def test_the_shipped_calibration_config_loads() -> None:
    from population_synthetic.analysis.cost_efficiency.raw_cost import load_cost_calibration

    doc = load_cost_calibration()
    assert doc["cost_basis"] == "calibrated_openrouter_2026-08-21"
    # The basis must differ from the measured one, or a consumer summing the two
    # could not tell an estimate from a measurement.
    assert doc["cost_basis"] != "generated_pool_01_raw"
    assert set(doc["models"]) == {"claude_haiku", "claude_sonnet"}
    for entry in doc["models"].values():
        assert len(entry["methods"]) == 5
        for row in entry["methods"].values():
            assert row["usd_per_persona"] > 0
            assert row["n"] == 10


def test_a_calibrated_cell_resolves_and_an_uncalibrated_one_returns_none() -> None:
    from population_synthetic.analysis.cost_efficiency.raw_cost import (
        calibrated_persona_cost,
        load_cost_calibration,
    )

    doc = load_cost_calibration()
    hit = calibrated_persona_cost("claude_haiku", "all_pick_v2", doc)
    assert hit is not None
    per_persona, basis = hit
    assert per_persona > 0 and basis == doc["cost_basis"]
    # Every other model prices from its own telemetry; absence is the normal case.
    assert calibrated_persona_cost("openrouter_kimi_k3", "all_pick_v2", doc) is None


def test_a_calibrated_model_missing_a_method_raises() -> None:
    from population_synthetic.analysis.cost_efficiency.raw_cost import calibrated_persona_cost

    doc = {"cost_basis": "x", "models": {"m": {"methods": {"a": {"usd_per_persona": 1.0}}}}}
    # Silently returning None here would read downstream as "this cell had no cost"
    # when in truth nobody measured it -- the exact zero-vs-absent confusion.
    with pytest.raises(ValueError, match="calibrated but has no entry"):
        calibrated_persona_cost("m", "b", doc)
