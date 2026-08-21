"""raw_cost.py -- total one combination's LLM cost over the **full generated pool**.

Reads the per-persona ``llm_interactions.{jsonl,json}`` telemetry under
``{output_base}/01_Raw/{slug}/persona_*/``, sums the tokens every call in the run
actually consumed, and prices them through ``config/analysis/model_pricing.yaml``.

**Why the full pool.** ``generation_metadata`` totals the same telemetry over the
capped mirror (``03_Analysis/population_cap/``), i.e. over the ~100 personas a
combination was subsampled down to. That is the wrong denominator for a cost figure
twice over: the discarded personas were paid for, and they are discarded *at a rate
that varies by model* -- one live combination generated 549 personas to keep 100 --
so a capped cost figure understates the wasteful models most. A withdrawn
combination has no capped mirror at all and would simply be absent. This module is
the correction, and it lives here rather than in ``generation_metadata`` so that
process's shipped read contract is not touched.

Boundaries. This module knows nothing about fidelity, ranking, charts, the capped
mirror, or the slug's axis decomposition. It takes an ``output_base``, a ``slug`` and
the combination's ``model_id`` (the pricing join key, supplied by the caller because
the slug -> model decomposition is the loader's business and this module holds no
axis registry) and returns one :class:`RawCostTotals`.

**Pricing is read here, not imported.** ``generation_metadata/pricing.py`` parses the
same config and would otherwise be the accessor to reuse, but importing any submodule
of that package executes its ``__init__``, which imports
``analysis.utils.capped_source.resolve_stage_source`` -- the capped-mirror reader this
module exists to avoid. Importing it would put the capped mirror back in this module's
import graph, so a minimal reader lives here instead. Both readers parse one config
file, which remains the single source of truth.

Four facts are kept apart because collapsing any two of them corrupts the figure
downstream (guide 03 sect. 6 -- zero is not absent):

* **absent** -- the combination reported no token telemetry at all. ``has_token_data``
  is ``False`` and ``total_cost_usd`` is ``None``. Never ``0.0``: it is not a claim
  that the run was free, it is the absence of any claim.
* **unmetered** -- the model is priced ``{in: 0, out: 0}`` (the nine ``ollama_*``
  local models, about a third of the axis). ``unmetered`` is ``True`` and, when
  telemetry exists, ``total_cost_usd`` is a *measured* ``0.0``. Unmetered is not free:
  local inference has a real cost the pricing config does not model, and the flag
  travels as data so a consumer renders that caveat rather than implying zero cost.
* **priced** -- a rate is configured and non-zero; the cost is the summed tokens
  through it.
* **unpriceable** -- the model has no entry in the pricing table at all. This
  **raises**, always, and before any telemetry is read: a run whose cost cannot be
  computed must surface as a config gap, never as a zero or an absence that looks
  like thin telemetry.

**Double counting.** A run may have been aborted and resumed. The generator truncates
``llm_interactions.jsonl`` if and only if it discards the persona's checkpoint, which
is precisely what keeps ``(persona_id, call_index)`` unique without any downstream
dedupe. This module *asserts* that invariant on read and raises on a duplicate, naming
the persona, the offending file and the file the key was first seen in -- summing a
file whose append/truncate discipline broke would silently inflate every cost in the
figure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from population_synthetic._paths import PROJECT_ROOT

__all__ = [
    "COST_BASIS",
    "INTERACTION_FILENAMES",
    "PRICING_PATH",
    "RAW_STAGE_DIR",
    "PricingProvenance",
    "RawCostTotals",
    "RawPricing",
    "load_raw_pricing",
    "pricing_document",
    "raw_cost_for_slug",
]

#: The raw-generation stage folder. Mirrors the literal the generator writes to
#: (``manifest_loader.compose_manifest``: ``{output_base}/01_Raw/{slug}``); it is a
#: structural constant of the pipeline layout, not a tunable value. Declared locally,
#: as ``generation_metadata/__init__.py`` and ``scripts/analyze/cap_populations.py``
#: both do -- there is no shared accessor for it.
#: Config declaring the token-telemetry plausibility floor. A literal here would
#: be a tuning constant hiding in code; the JSON carries the measurement that
#: justifies the number and the reason it exists.
TELEMETRY_CONFIG_PATH = (
    PROJECT_ROOT / "config" / "analysis" / "cost_efficiency" / "telemetry.json"
)

RAW_STAGE_DIR = "01_Raw"

#: Combo subdirectories holding one persona each.
PERSONA_GLOB = "persona_*"

#: The two on-disk shapes of the interaction log, in preference order. Written by
#: ``generators/synthetic/llm_interaction_log.py`` (JSONL); the JSON-array form is a
#: legacy layout still present in older runs.
INTERACTION_FILENAMES = ("llm_interactions.jsonl", "llm_interactions.json")

#: The name of the persona population every cost here is measured over. Carried on
#: every record so the basis travels as data, not as prose in a chart caption -- a
#: cost number read without its basis is uninterpretable, and the alternative basis
#: (the capped mirror) differs from this one by up to 5.5x.
COST_BASIS = "generated_pool_01_raw"

#: The pricing config. Same file ``generation_metadata`` reads; see the module
#: docstring for why it is parsed here rather than imported.
PRICING_PATH = PROJECT_ROOT / "config" / "analysis" / "model_pricing.yaml"

#: Top-level keys the pricing config must declare.
_REQUIRED_TOP_KEYS = ("observed_date", "source", "currency", "models")

#: Rates are quoted per 1,000,000 tokens.
_PER_MILLION = 1_000_000.0

#: Per-call token fields summed into the combination totals.
_INPUT_TOKEN_FIELD = "prompt_tokens"
_OUTPUT_TOKEN_FIELD = "completion_tokens"
_TOTAL_TOKEN_FIELD = "total_tokens"
_CACHE_READ_FIELD = "cache_read_tokens"
_CACHE_CREATION_FIELD = "cache_creation_tokens"

#: Bracketed caveat tags in the pricing config's inline comments, e.g.
#: ``[VERIFY]``, ``[effective/discounted]``, ``[verified 2026-08-14]``. The config's
#: own header instructs the reader to verify flagged rows *before using cost figures
#: in a publication*, which is exactly what this process produces -- so the tags are
#: lifted out of the comments and carried as data (ADR 2026-08-07: caveats travel as
#: fields and columns, because the tables travel without the code).
_TAG_RE = re.compile(r"\[([^\]]+)\]")

#: Remedy named in the raise when a combination has no raw pool on disk.
_MISSING_POOL_REMEDY = (
    "re-run the generation for this combination "
    "(scripts/generate/generate_identities_parallel.py) or drop it from the analysis set"
)


@dataclass(frozen=True)
class PricingProvenance:
    """Where the prices came from and what the config says about trusting them.

    ``observed_date``/``source``/``currency`` are the config's own bulk-snapshot
    stamps. ``flags`` maps a model id to the bracketed tags found in that row's
    inline comment; a model with no tags maps to an empty tuple, which is a
    *positive* statement that the row is untagged rather than a missing key.
    """

    observed_date: str
    source: str
    currency: str
    config_path: str
    flags: Mapping[str, tuple[str, ...]]

    def flags_for(self, model_id: str) -> tuple[str, ...]:
        """Return the caveat tags recorded against *model_id* (empty tuple if none)."""
        return tuple(self.flags.get(model_id, ()))


@dataclass(frozen=True)
class RawPricing:
    """The pricing table plus its provenance, USD per 1,000,000 tokens."""

    rates: Mapping[str, tuple[float, float]]
    provenance: PricingProvenance
    #: Prompt-cache multipliers relative to the base input rate, e.g.
    #: ``{"read": 0.1, "write": 1.25}``. ``None`` when the config omits the block --
    #: consulted only when a run actually reports cache tokens.
    cache_multipliers: Mapping[str, float] | None = None

    def rate_for(self, model_id: str) -> tuple[float, float]:
        """Return ``(price_in, price_out)`` for *model_id*; raise when absent.

        Absent pricing is a config gap, never a zero: an unpriced model would be
        indistinguishable from an unmetered one in every downstream figure.
        """
        if model_id not in self.rates:
            raise KeyError(
                f"Model id {model_id!r} has no entry in the pricing table "
                f"({self.provenance.config_path}). Cost over the generated pool cannot be "
                f"computed for it. Add a '{model_id}: {{in, out}}' row (use {{in: 0, out: 0}} "
                f"only if the model is genuinely unmetered). "
                f"Known ids: {sorted(self.rates)}."
            )
        return self.rates[model_id]

    def is_unmetered(self, model_id: str) -> bool:
        """True when *model_id* is priced at zero on both sides; raises when absent.

        A property of the pricing config alone -- independent of whether the run
        produced any telemetry.
        """
        price_in, price_out = self.rate_for(model_id)
        return price_in == 0.0 and price_out == 0.0

    def cache_mults(self) -> tuple[float, float]:
        """Return ``(read_mult, write_mult)``; raise when the config omits the block."""
        if self.cache_multipliers is None:
            raise ValueError(
                "Cache tokens were reported by the run but the pricing table has no "
                f"'cache_multipliers' block ({self.provenance.config_path}). Add a top-level "
                "'cache_multipliers: {read, write}'."
            )
        return self.cache_multipliers["read"], self.cache_multipliers["write"]


@dataclass(frozen=True)
class RawCostTotals:
    """One combination's cost over the full generated pool.

    Every rate-like field ships beside the counts it was computed from (guide 03
    sect. 4), and every absent quantity is ``None`` rather than ``0`` (guide 03
    sect. 6). ``cost_basis`` names the population the total was measured over, so no
    consumer can print the number without it.
    """

    slug: str
    model: str
    cost_basis: str
    #: ``persona_*`` directories on disk -- the generated pool.
    n_personas: int
    #: How many of them carried an interaction log at all.
    n_personas_with_interactions: int
    #: How many of them reported at least one prompt/completion token count.
    n_personas_with_tokens: int
    #: Interaction records summed.
    n_calls: int
    #: Records lacking a ``call_index``, and therefore outside the uniqueness
    #: assertion. Carried as data so the limit of the double-counting guard is
    #: visible in the artifact rather than only in this docstring.
    n_unkeyed_calls: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    #: True when any persona reported prompt or completion tokens -- the same
    #: predicate ``generation_metadata`` publishes per combo. Gates the cost.
    has_token_data: bool
    #: Why the telemetry was rejected as implausible, or ``None`` when it was not.
    #: Present-but-too-small counts become absent; the reason travels as data so a
    #: reader of the artifact sees why a combination has no cost.
    implausible_telemetry: str | None
    #: True when the model is priced ``{in: 0, out: 0}``. Unmetered is not free.
    unmetered: bool
    price_in: float
    price_out: float
    #: Caveat tags from the pricing config's row for this model.
    pricing_flags: tuple[str, ...]
    #: ``None`` when ``has_token_data`` is False -- absent, not zero. A measured
    #: ``0.0`` means the model is unmetered and the run did report tokens.
    total_cost_usd: float | None


def _tags_by_model(text: str) -> dict[str, tuple[str, ...]]:
    """Lift the bracketed caveat tags out of the ``models:`` block's inline comments.

    YAML comments are dropped by the parser, so the config's own "[VERIFY] before
    using cost figures in a publication" instruction is invisible to ``safe_load``.
    This scans the raw text for the ``models:`` block and records, per model row, the
    bracketed tags in its trailing comment. Values in that block are inline flow
    mappings with no ``#`` in them, so the first ``#`` on a row starts its comment.
    """
    tags: dict[str, tuple[str, ...]] = {}
    in_models = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_models:
            if stripped == "models:":
                in_models = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        # A non-indented line ends the block.
        if not line[:1].isspace():
            break
        if "#" not in line:
            continue
        body, _, comment = line.partition("#")
        key, sep, _ = body.partition(":")
        if not sep:
            continue
        tags[key.strip()] = tuple(m.strip() for m in _TAG_RE.findall(comment))
    return tags


def _coerce_rate(model_id: str, entry: Any, cfg_path: Path) -> tuple[float, float]:
    """Validate one ``{in, out}`` rate entry and return it as floats."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"Pricing entry for {model_id!r} must be a mapping with 'in'/'out', "
            f"got {type(entry).__name__}: {cfg_path}"
        )
    missing = [k for k in ("in", "out") if k not in entry]
    if missing:
        raise ValueError(
            f"Pricing entry for {model_id!r} missing required key(s) {missing}: {cfg_path}"
        )
    try:
        price_in = float(entry["in"])
        price_out = float(entry["out"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Pricing entry for {model_id!r} has non-numeric rate(s): {entry!r} ({cfg_path})"
        ) from exc
    if price_in < 0 or price_out < 0:
        raise ValueError(
            f"Pricing entry for {model_id!r} has a negative rate: {entry!r} ({cfg_path})"
        )
    return (price_in, price_out)


def _coerce_cache_multipliers(raw: Mapping[str, Any], cfg_path: Path) -> dict[str, float] | None:
    """Validate the optional ``cache_multipliers`` block, or return ``None``."""
    block = raw.get("cache_multipliers") if "cache_multipliers" in raw else None
    if block in (None, ""):
        return None
    if not isinstance(block, dict):
        raise ValueError(
            f"'cache_multipliers' must be a mapping with 'read'/'write', "
            f"got {type(block).__name__}: {cfg_path}"
        )
    missing = [k for k in ("read", "write") if k not in block]
    if missing:
        raise ValueError(f"'cache_multipliers' missing required key(s) {missing}: {cfg_path}")
    try:
        read_mult = float(block["read"])
        write_mult = float(block["write"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"'cache_multipliers' has non-numeric value(s): {block!r} ({cfg_path})"
        ) from exc
    if read_mult < 0 or write_mult < 0:
        raise ValueError(f"'cache_multipliers' has a negative value: {block!r} ({cfg_path})")
    return {"read": read_mult, "write": write_mult}


def load_raw_pricing(path: Path | str | None = None) -> RawPricing:
    """Load ``config/analysis/model_pricing.yaml`` with its provenance (fail-fast).

    Parameters
    ----------
    path:
        Optional override; defaults to :data:`PRICING_PATH`.

    Raises
    ------
    FileNotFoundError
        When the config file does not exist.
    ValueError
        When the file is not a mapping, is missing a required top-level key, has an
        empty or malformed ``models`` block, or a malformed rate entry.
    """
    cfg_path = Path(path) if path is not None else PRICING_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Model pricing config not found: {cfg_path}")

    text = cfg_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError(
            f"Model pricing config must be a mapping, got {type(raw).__name__}: {cfg_path}"
        )

    missing = [k for k in _REQUIRED_TOP_KEYS if k not in raw or raw[k] in (None, "")]
    if missing:
        raise ValueError(
            f"Model pricing config missing required top-level key(s) {missing}: {cfg_path}"
        )

    models = raw["models"]
    if not isinstance(models, dict) or not models:
        raise ValueError(f"Model pricing config missing non-empty 'models' mapping: {cfg_path}")

    rates = {
        str(model_id): _coerce_rate(str(model_id), entry, cfg_path)
        for model_id, entry in models.items()
    }
    tags = _tags_by_model(text)
    provenance = PricingProvenance(
        observed_date=str(raw["observed_date"]),
        source=str(raw["source"]),
        currency=str(raw["currency"]),
        config_path=str(cfg_path),
        flags={model_id: tags.get(model_id, ()) for model_id in rates},
    )
    return RawPricing(
        rates=rates,
        provenance=provenance,
        cache_multipliers=_coerce_cache_multipliers(raw, cfg_path),
    )


def pricing_document(pricing: RawPricing, model_ids: Sequence[str]) -> dict[str, Any]:
    """The JSON-ready pricing-provenance block for the models actually analysed.

    Carries the bulk-snapshot stamps plus the per-model caveat tags, restricted to
    the models in the report so the block documents *these* numbers rather than the
    whole config. ``unmetered`` is stated per model here too, because a reader of the
    JSON must be able to tell a measured zero from a missing price without holding
    the pricing file. Deterministic (sorted, no timestamp), so a report built twice
    from one input is byte-identical.
    """
    ordered = sorted(set(model_ids))
    return {
        "observed_date": pricing.provenance.observed_date,
        "source": pricing.provenance.source,
        "currency": pricing.provenance.currency,
        "config_path": pricing.provenance.config_path,
        "cost_basis": COST_BASIS,
        "models": {
            model_id: {
                "price_in": pricing.rate_for(model_id)[0],
                "price_out": pricing.rate_for(model_id)[1],
                "unmetered": pricing.is_unmetered(model_id),
                "flags": list(pricing.provenance.flags_for(model_id)),
            }
            for model_id in ordered
        },
    }


def _find_interaction_file(persona_dir: Path) -> Path | None:
    """Return the persona's interaction log, or ``None`` when it has none."""
    for name in INTERACTION_FILENAMES:
        candidate = persona_dir / name
        if candidate.exists():
            return candidate
    return None


def _parse_records(path: Path) -> list[dict[str, Any]]:
    """Parse an interaction log (JSONL, or the legacy JSON-array form)."""
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON array in {path}, got {type(data).__name__}")
        records = data
    else:
        records = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {lineno} of {path}: {exc}") from exc
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(
                f"Interaction records must be JSON objects, got {type(record).__name__}: {path}"
            )
    return records


def _token_value(record: Mapping[str, Any], field: str, path: Path) -> int | None:
    """Read one token field as an ``int``, or ``None`` when the call did not report it.

    Validated at the boundary rather than coerced later: a token count that arrived
    as a string or a float would otherwise propagate a type into the cost arithmetic
    (guide 02 sect. 3, numeric type stability).
    """
    if field not in record:
        return None
    value = record[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"Interaction field {field!r} must be an integer token count or null, "
            f"got {value!r} ({type(value).__name__}) in {path}"
        )
    if value < 0:
        raise ValueError(f"Interaction field {field!r} is negative ({value}) in {path}")
    return value


def _persona_dirs(slug_dir: Path) -> list[Path]:
    """The combination's ``persona_*`` subdirectories, lexicographically sorted."""
    return sorted((p for p in slug_dir.glob(PERSONA_GLOB) if p.is_dir()), key=lambda p: p.name)


def load_telemetry_floor(path: str | Path = TELEMETRY_CONFIG_PATH) -> int:
    """The minimum believable mean input tokens per call, from config (fail-fast).

    Raises :class:`FileNotFoundError` when the config is missing and
    :class:`ValueError` when ``min_input_tokens_per_call`` is absent or is not a
    positive integer. There is no default: a silent fallback would decide, without
    saying so, which provider's telemetry is trusted.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Telemetry config not found: {path}. Expected "
            "config/analysis/cost_efficiency/telemetry.json."
        )
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    floor = raw.get("min_input_tokens_per_call") if isinstance(raw, dict) else None
    if not isinstance(floor, int) or isinstance(floor, bool) or floor <= 0:
        raise ValueError(
            f"Telemetry config {path} must carry a positive integer "
            f"'min_input_tokens_per_call', got {floor!r}."
        )
    return floor


def raw_cost_for_slug(
    output_base: Path | str,
    slug: str,
    model_id: str,
    pricing: RawPricing,
) -> RawCostTotals:
    """Total one combination's LLM cost over its full ``01_Raw`` pool.

    Parameters
    ----------
    output_base:
        The pipeline output root; the pool is ``{output_base}/01_Raw/{slug}/``.
    slug:
        The combination's run slug, ``{country}_{strategy}_{model}``.
    model_id:
        The model axis id -- the pricing join key. Passed in rather than derived
        here: decomposing a slug needs the axis registries, which are the caller's
        business (``analysis/utils/axes.decompose_slug``), not this module's.
    pricing:
        A table from :func:`load_raw_pricing`.

    Returns
    -------
    RawCostTotals
        Cost and token totals over the generated pool, with ``cost_basis`` set to
        :data:`COST_BASIS`.

    Raises
    ------
    KeyError
        When *model_id* has no pricing entry. Raised **before** any telemetry is
        read, so an unpriceable model fails identically whether or not the run
        produced tokens.
    FileNotFoundError
        When the combination has no ``01_Raw`` pool directory.
    ValueError
        When an interaction log is malformed, carries a non-integer token count, or
        repeats a ``(persona_id, call_index)`` key -- the last being the
        aborted-and-resumed double-counting guard.
    """
    price_in, price_out = pricing.rate_for(model_id)  # raises first, by design
    unmetered = price_in == 0.0 and price_out == 0.0

    slug_dir = Path(output_base) / RAW_STAGE_DIR / slug
    if not slug_dir.is_dir():
        raise FileNotFoundError(
            f"No raw generation pool for combination {slug!r}: {slug_dir} does not exist. "
            f"Cost over the generated pool cannot be computed -- {_MISSING_POOL_REMEDY}."
        )

    persona_dirs = _persona_dirs(slug_dir)
    seen_keys: dict[tuple[str, int], Path] = {}
    n_calls = 0
    n_unkeyed_calls = 0
    n_with_interactions = 0
    n_with_tokens = 0
    sums: dict[str, int] = {}
    reported: set[str] = set()

    token_fields = (
        _INPUT_TOKEN_FIELD,
        _OUTPUT_TOKEN_FIELD,
        _TOTAL_TOKEN_FIELD,
        _CACHE_READ_FIELD,
        _CACHE_CREATION_FIELD,
    )

    for persona_dir in persona_dirs:
        log_path = _find_interaction_file(persona_dir)
        if log_path is None:
            continue
        n_with_interactions += 1
        persona_has_tokens = False
        for record in _parse_records(log_path):
            n_calls += 1
            # The persona directory *is* the persona identity; the record's own
            # persona_id is preferred so a mis-filed log collides rather than hides.
            persona_id = record.get("persona_id") or persona_dir.name
            call_index = record.get("call_index")
            if isinstance(call_index, int) and not isinstance(call_index, bool):
                key = (str(persona_id), call_index)
                first_seen = seen_keys.get(key)
                if first_seen is not None:
                    raise ValueError(
                        f"Duplicate LLM call (persona_id={persona_id!r}, call_index={call_index}) "
                        f"in combination {slug!r}: seen in {first_seen} and again in {log_path}. "
                        "(persona_id, call_index) must be unique across the pool -- the generator "
                        "truncates llm_interactions.jsonl iff it discards the checkpoint, so a "
                        "repeat means an aborted-and-resumed run appended onto a kept log and "
                        "every token in it would be counted twice. Re-generate this persona with "
                        "--force, or delete the duplicated log."
                    )
                seen_keys[key] = log_path
            else:
                n_unkeyed_calls += 1
            for field in token_fields:
                value = _token_value(record, field, log_path)
                if value is None:
                    continue
                reported.add(field)
                sums[field] = sums.get(field, 0) + value
                if field in (_INPUT_TOKEN_FIELD, _OUTPUT_TOKEN_FIELD):
                    persona_has_tokens = True
        if persona_has_tokens:
            n_with_tokens += 1

    def total(field: str) -> int | None:
        """Summed field, or ``None`` when no call in the pool reported it."""
        return sums.get(field, 0) if field in reported else None

    input_tokens = total(_INPUT_TOKEN_FIELD)
    output_tokens = total(_OUTPUT_TOKEN_FIELD)
    cache_read_tokens = total(_CACHE_READ_FIELD)
    cache_creation_tokens = total(_CACHE_CREATION_FIELD)
    has_token_data = input_tokens is not None or output_tokens is not None

    # A present-but-implausible input count is worse than an absent one: priced,
    # it yields a confidently wrong dollar figure that nothing downstream can
    # detect. Below the configured floor the telemetry is recorded as absent,
    # with the reason carried on the record.
    implausible_reason: str | None = None
    if has_token_data and n_calls > 0 and input_tokens is not None:
        per_call = input_tokens / n_calls
        floor = load_telemetry_floor()
        if per_call < floor:
            implausible_reason = (
                f"mean input tokens per call {per_call:.1f} is below the plausibility "
                f"floor of {floor}; the provider does not report usage, so the counts "
                f"are treated as absent rather than priced"
            )
            has_token_data = False

    if not has_token_data:
        total_cost_usd = None
    else:
        cost = (input_tokens or 0) * price_in / _PER_MILLION
        cost += (output_tokens or 0) * price_out / _PER_MILLION
        if cache_read_tokens or cache_creation_tokens:
            read_mult, write_mult = pricing.cache_mults()
            cost += (cache_read_tokens or 0) * price_in * read_mult / _PER_MILLION
            cost += (cache_creation_tokens or 0) * price_in * write_mult / _PER_MILLION
        total_cost_usd = cost

    return RawCostTotals(
        slug=slug,
        model=model_id,
        cost_basis=COST_BASIS,
        n_personas=len(persona_dirs),
        n_personas_with_interactions=n_with_interactions,
        n_personas_with_tokens=n_with_tokens,
        n_calls=n_calls,
        n_unkeyed_calls=n_unkeyed_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total(_TOTAL_TOKEN_FIELD),
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        has_token_data=has_token_data,
        implausible_telemetry=implausible_reason,
        unmetered=unmetered,
        price_in=price_in,
        price_out=price_out,
        pricing_flags=pricing.provenance.flags_for(model_id),
        total_cost_usd=total_cost_usd,
    )
