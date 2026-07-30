"""
generate_identities_parallel.py -- Generate N persona identities in parallel.

Usage:
    # Via manifest (recommended):
    python scripts/generate/generate_identities_parallel.py \
        --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml

    # Via manifest with CLI overrides:
    python scripts/generate/generate_identities_parallel.py \
        --manifest config/synthetic/manifests/identity_manifest_014_claude_haiku.yaml \
        --n 10 --workers 4

    # Via axis IDs (composable experiment config):
    python scripts/generate/generate_identities_parallel.py \
        --model-id claude_haiku \
        --strategy-id all_pick \
        --country-id swedish

    # Via axis IDs with overrides and force regeneration:
    python scripts/generate/generate_identities_parallel.py \
        --model-id ollama_llama33_70b \
        --strategy-id all_generate_evaluate_pick \
        --country-id swedish \
        --n 50 \
        --workers 4 \
        --force

    # Via explicit CLI args:
    python scripts/generate/generate_identities_parallel.py \
        --mode configurable \
        --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json \
        --strategy config/synthetic/axes/strategies/_compared_only_generate_evaluate_random_pick.yaml \
        --n 100 \
        --workers 8 \
        --output-dir data/identity/config_004_n100

    python scripts/generate/generate_identities_parallel.py \
        --provider claude \
        --mode configurable \
        --config config/synthetic/simulation_configs/simulation_config_004_swedish_generative.json \
        --strategy config/synthetic/axes/strategies/_compared_only_generate_evaluate_random_pick.yaml \
        --n 100 \
        --workers 8 \
        --output-dir data/identity/config_004_n100_claude
"""

import argparse
import atexit
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from population_synthetic.analysis.validate_raw.validate import expected_raw_keys
from population_synthetic.clients.ollama_control_client import OllamaControlClient
from population_synthetic.clients.retry_policy import MAX_RETRY_ATTEMPTS
from population_synthetic.generators.synthetic import ollama_concurrency, ollama_hosts
from population_synthetic.generators.synthetic.factory_identity_generator import FactoryIdentityGenerator
from population_synthetic.generators.synthetic.identity_generator_configurable import resolve_category_order
from population_synthetic.generators.synthetic.llm_interaction_log import LLMInteractionCollector
from population_synthetic.generators.synthetic.manifest_loader import (
    compose_manifest,
    load_manifest,
    serialize_manifest,
)

_SCRIPT_START_TIME = time.time()

_LOG_FORMAT = "%(asctime)s %(levelname)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"+{seconds:.1f}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"+{m}m{s:02d}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"+{h}h{m:02d}m{s:02d}s"
    d, h = divmod(h, 24)
    return f"+{d}d{h:02d}h{m:02d}m{s:02d}s"


class _ElapsedFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        base = super().formatTime(record, datefmt)
        return f"{base} [{_fmt_elapsed(record.created - _SCRIPT_START_TIME)}]"


_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_ElapsedFormatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
logging.basicConfig(level=logging.INFO, handlers=[_console_handler])
logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()
_completed = 0
_failed = 0

_active_clients: set = set()
_active_clients_lock = threading.Lock()


def _atexit_cleanup() -> None:
    with _active_clients_lock:
        clients = list(_active_clients)
    for client in clients:
        try:
            client.close()
        except Exception:
            pass


atexit.register(_atexit_cleanup)


def _generate_one(
    index: int,
    total: int,
    mode: str,
    provider: str,
    model: str,
    config_path: str,
    output_dir: Path,
    kwargs: dict,
    log_llm: bool = False,
    base_url: str | None = None,
    api_key_env_var: str | None = None,
    generation_config: dict | None = None,
    force: bool = False,
    retry_until_success: bool = False,
    structured_output: bool = False,
) -> tuple[int, bool, str]:
    global _completed, _failed

    persona_dir = output_dir / f"persona_{index:05d}"
    out_file = persona_dir / "identity.json"

    if not force and out_file.exists():
        with _progress_lock:
            _completed += 1
        return index, True, "skipped (exists)"

    cfg = generation_config or {}

    client = None
    generator = None
    # The client imports below stay function-local on purpose (unlike the
    # module-scope imports at the top of this file): gemini_client pulls the
    # `google` SDK and openai_compat_client pulls `openai`. Hoisting them would
    # make every run import both third-party SDKs -- including --provider ollama,
    # which needs neither -- and hard-fail when either is not installed.
    try:
        if provider == "gemini":
            from population_synthetic.clients.gemini_client import GeminiClient
            client = GeminiClient(model_name=model, default_config=cfg)
        elif provider == "claude":
            from population_synthetic.clients.claude_code_client import ClaudeCodeClient
            client = ClaudeCodeClient(model_name=model, default_config=cfg)
            with _active_clients_lock:
                _active_clients.add(client)
        elif provider == "ollama":
            from population_synthetic.clients.ollama_client import OllamaClient
            client = OllamaClient(model_name=model, base_url=base_url, default_config=cfg)
            with _active_clients_lock:
                _active_clients.add(client)
        elif provider == "openai_compat":
            from population_synthetic.clients.openai_compat_client import OpenAICompatClient
            if not base_url:
                raise ValueError("base_url is required for provider 'openai_compat'")
            client = OpenAICompatClient(
                model_name=model,
                base_url=base_url,
                api_key_env_var=api_key_env_var or "OPENAI_API_KEY",
                default_config=cfg,
            )
            with _active_clients_lock:
                _active_clients.add(client)
        elif provider == "openrouter":
            from population_synthetic.clients.openai_compat_client import OpenAICompatClient
            # base_url and api_key_env_var are structural defaults; axis files may override.
            client = OpenAICompatClient(
                model_name=model,
                base_url=base_url or "https://openrouter.ai/api/v1",
                api_key_env_var=api_key_env_var or "OPENROUTER_API_KEY",
                default_config=cfg,
                provider_tag="openrouter",
                default_headers={"X-Title": "population-synthetic"},
            )
            with _active_clients_lock:
                _active_clients.add(client)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Expected 'gemini', 'claude', 'ollama', 'openai_compat', or 'openrouter'.")
        # The transport layer honours the same flag as the generator, so a flaky
        # endpoint is ridden out inside the client instead of costing the persona
        # every category resolved so far (see clients/retry_policy.py). Clients
        # without a retry loop simply never read it.
        client.retry_until_success = retry_until_success
        generator = FactoryIdentityGenerator.create_generator(mode, client)
        generator.retry_until_success = retry_until_success
        generator.use_structured_output = structured_output
        # Correlation key for exact log<->JSONL joining; matches persona_dir name.
        if hasattr(generator, "persona_id"):
            generator.persona_id = f"persona_{index:05d}"
        if log_llm:
            generator.interaction_collector = LLMInteractionCollector(
                persona_dir / "llm_interactions.jsonl"
            )

        identity_data, _ = generator.generate_identity(config_path, **kwargs)

        persona_dir.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(identity_data, f, indent=2, ensure_ascii=False)

        with _progress_lock:
            _completed += 1
            c, fa = _completed, _failed
        logger.info("──── ✓ [%d/%d] persona_%05d OK ──── (failed so far: %d)", c, total, index, fa)
        return index, True, "ok"

    except Exception as e:
        with _progress_lock:
            _failed += 1
            c, fa = _completed, _failed
        logger.error("──── ✗ [%d/%d] persona_%05d FAIL ──── %s  (failed so far: %d)", c, total, index, e, fa)
        return index, False, str(e)

    finally:
        if generator is not None and generator.interaction_collector:
            generator.interaction_collector.close()
        if client is not None and hasattr(client, "close"):
            client.close()
            with _active_clients_lock:
                _active_clients.discard(client)


# The reconfigure outcomes after which the server's parallelism matches the run.
# In both, the registry's declared server_num_parallel is stale rather than
# violated, so the warning built on it no longer describes anything true.
_TUNED_OUTCOMES = (
    ollama_concurrency.OUTCOME_ALREADY_CORRECT,
    ollama_concurrency.OUTCOME_APPLIED,
)


def _ollama_preflight(
    ollama_host: ollama_hosts.OllamaHost | None,
    provider: str,
    model: str,
    workers: int,
    *,
    requested: bool,
    control_client_factory: Any | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    """Tune and warm the run's Ollama host once, and return what actually happened.

    Returns the three pre-flight facts as separate serializable blocks
    (``reconfigure``, ``warm_up``, ``readiness``), plus the raw before/after server
    snapshots the verdicts were reached from (``server_state``), each ``None`` when
    that fact was never established. The three verdicts are kept apart because they
    are independent: a run can have its parallelism applied, fail to warm the model,
    and still be ready.

    Decision on record -- a generation run is permitted to restart shared
    infrastructure. Context: the host's container also serves Open WebUI and, on the
    Linux host, ComfyUI, and ``OLLAMA_NUM_PARALLEL`` can only be changed by recreating
    it. Decision: reconfigure anyway, because the run is about to monopolise that GPU
    for minutes regardless, and running it mis-tuned wastes the same GPU for roughly
    twice as long. Consequences, and the three things that bound the blast radius: the
    skip check means a correctly-configured server is never touched; the call happens
    once, before generation, never between personas; and the whole step is opt-in
    (``--ollama-reconfigure``, off by default). No locking or in-use detection is
    attempted -- ``/status`` reports ``container_running``, not whether someone else's
    request is in flight.

    Failure is tolerated but never swallowed. The run is correct at any parallelism,
    only slower, so nothing here aborts it; instead every outcome is recorded verbatim
    in ``run_metadata.json`` so a later timing analysis can filter on it rather than
    silently pooling a run that queued with one that batched.

    Stage logging happens inside :func:`ollama_concurrency.preflight`, which emits one
    line per stage at the level that stage deserves. Only what never reaches the policy
    layer is logged here: the skipped path, and the drift check's verdict -- the policy
    function returns that one as a value for this layer to voice, so both its outcomes
    are voiced in the same place.
    """
    record: dict[str, Any] = {"reconfigure": None, "warm_up": None, "readiness": None, "server_state": None}

    if not requested or provider != "ollama":
        return record

    if ollama_host is None or ollama_host.control_url is None:
        # Nothing to talk to: either the host declares no control endpoint, or
        # --base-url pointed this run at a machine the registry does not describe.
        # Never reconfigure a host the run is not using -- the outputs would look
        # normal while another GPU was restarted.
        outcome = ollama_concurrency.ensure_num_parallel(None, model, workers)
        logger.warning("Ollama pre-flight skipped (%s): %s", outcome.outcome, outcome.detail)
        record["reconfigure"] = asdict(outcome)
        return record

    factory = OllamaControlClient if control_client_factory is None else control_client_factory
    client = factory(ollama_host.control_url)
    try:
        drift = ollama_concurrency.check_worker_drift(client, model, workers)
        if drift is not None:
            logger.warning("%s", drift)
        else:
            # A drift check that agreed and a drift check that never ran look the same
            # from the console unless agreement says so out loud. With a client bound,
            # None is documented to mean exactly one thing: the two values match.
            logger.info(
                "Ollama pre-flight drift check: config's %d workers for %s agrees with %s/models.",
                workers,
                model,
                ollama_host.control_url,
            )
        outcome = ollama_concurrency.preflight(
            client, ollama_host.base_url, model, workers, session=session
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    record["reconfigure"] = asdict(outcome.reconfigure)
    record["warm_up"] = asdict(outcome.warm_up)
    record["readiness"] = asdict(outcome.readiness)
    # The evidence beside the verdicts: what the host looked like before this run
    # touched it and what it looked like afterwards, each field null where the fact
    # could not be established. Serialised the same way as the three blocks above.
    record["server_state"] = {
        "before": asdict(outcome.state_before),
        "after": asdict(outcome.state_after),
    }
    return record


def _server_parallelism_is_tuned(preflight_record: dict[str, Any]) -> bool:
    """Whether the pre-flight left the server's OLLAMA_NUM_PARALLEL matching this run."""
    reconfigure = preflight_record["reconfigure"]
    return reconfigure is not None and reconfigure["outcome"] in _TUNED_OUTCOMES


def _assert_strategy_covers_country(strategy_path: Path, strategy_id: str, country_id: str) -> None:
    """Reject an axis combo whose strategy cannot produce what the country requires.

    A strategy declares a category set; a country declares (via its mapping index,
    minus its deprecated attributes) the raw keys a persona must carry to pass the
    validation gate. Those two are versioned independently -- a v2 strategy drops
    ``birth_location``, which Sweden deprecated but Italy still analyses -- so the
    pairing is only valid when the categories cover the requirement. Without this
    check the mismatch surfaces far downstream as a 0% ``validate_raw`` pass rate
    and zero capped personas, after a full sweep has already been paid for.

    This lives at the orchestration edge rather than in ``compose_manifest``: the
    requirement is an analysis-layer fact (the mapping ``_index.json``, read through
    :func:`expected_raw_keys`), and ``generators/`` importing it would both invert the
    layer dependency and close an import cycle -- ``analysis.utils.country_config``
    already imports ``manifest_loader``. This script legitimately sees both layers.
    The category set is read with the generator's own
    :func:`resolve_category_order`, so the guard tests the categories a run would
    actually resolve rather than a second parse of the YAML.

    Raises:
        ValueError: If any required raw key is absent from the strategy's categories.
    """
    required = expected_raw_keys(country_id)
    generated = set(resolve_category_order(str(strategy_path)))
    missing = [key for key in required if key not in generated]
    if missing:
        raise ValueError(
            f"Incompatible axis combination: strategy {strategy_id!r} does not generate "
            f"{len(missing)} raw key(s) that country {country_id!r} requires: {missing}. "
            f"The requirement is the country's mapping index attributes minus its deprecated "
            f"attributes; pair {country_id!r} with a strategy whose categories cover them."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate N persona identities in parallel")
    parser.add_argument("--manifest", default=None, help="Path to a YAML manifest file (replaces all other arguments)")
    parser.add_argument("--model-id", default=None, help="Axis model ID (e.g., 'claude_haiku') — mutually exclusive with --manifest")
    parser.add_argument("--strategy-id", default=None, help="Axis strategy ID (e.g., 'all_pick') — mutually exclusive with --manifest")
    parser.add_argument("--country-id", default=None, help="Axis country ID (e.g., 'swedish') — mutually exclusive with --manifest")
    parser.add_argument("--mode", default=None, choices=["configurable"],
                        help="Identity generation strategy (currently only 'configurable' is supported)")
    parser.add_argument("--config", default=None, help="Flat schema / prompt config file")
    parser.add_argument("--strategy", default=None, help="Strategy definition file (required for configurable)")
    parser.add_argument("--n", type=int, default=None, help="Number of identities to generate")
    parser.add_argument("--workers", type=int, default=None, help="Max parallel workers (default: 8)")
    parser.add_argument(
        "--provider",
        default=None,
        choices=["gemini", "claude", "ollama", "openai_compat", "openrouter"],
        help="LLM provider to use: gemini, claude, ollama, openai_compat, or openrouter (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Model name override. Defaults: gemini -> gemini-2.5-flash, claude -> sonnet, "
            "ollama -> llama3.2, openai_compat -> mistral-large-latest, openrouter -> openai/gpt-4o"
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL for Ollama or OpenAI-compatible provider (overrides manifest and --ollama-host)",
    )
    parser.add_argument(
        "--ollama-host",
        default=None,
        choices=ollama_hosts.host_ids(),
        help="Ollama inference host id from config/synthetic/ollama_hosts.yaml. Selects the "
             "endpoint and the per-host worker count of the model axis file. Omitted: the "
             "registry's default_host. Inert for non-Ollama providers.",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="Name of the environment variable holding the API key for openai_compat provider (default: OPENAI_API_KEY)",
    )
    parser.add_argument("--output-dir", default=None, help="Output directory for persona_XXXXX/ folders")
    parser.add_argument(
        "--log-llm",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Log all raw LLM interactions (prompt + response) to llm_interactions.json per persona (default: on)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing personas instead of skipping",
    )
    parser.add_argument(
        "--retry-until-success",
        action="store_true",
        default=False,
        help="Retry every layer (transport, JSON parse, weight reconcile, persona slot) "
             f"up to {MAX_RETRY_ATTEMPTS} times instead of each layer's small default "
             "(default: disabled)",
    )
    parser.add_argument(
        "--structured-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use JSON-Schema–constrained decoding for Ollama (default: off)",
    )
    parser.add_argument(
        "--ollama-auto-workers",
        action="store_true",
        default=False,
        help="For Ollama models only: override --workers with the model axis file's "
             "parallel.workers value for the selected host (the per-model, per-GPU "
             "VRAM-optimal count). No-op for cloud providers. Default: off.",
    )
    parser.add_argument(
        "--ollama-reconfigure",
        action="store_true",
        default=False,
        help="For Ollama hosts declaring a control_url only: before generating, set the "
             "server's OLLAMA_NUM_PARALLEL to the resolved worker count (which restarts "
             "that host's container when the value differs) and warm the model up, so "
             "the first persona does not pay the cold load. Skipped -- and recorded as "
             "'no_control_url' -- for cloud providers, for --base-url runs, and for "
             "hosts declaring no control endpoint. Default: off.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Verbosity of both the console and the run log file. DEBUG adds the raw "
             "before/after Ollama server snapshots and every unreadable-endpoint "
             "detail the pre-flight tolerated. Default: INFO.",
    )
    args = parser.parse_args()

    # The *root* level is the only lever that works. A handler set to DEBUG below a
    # logger left at INFO is inert -- Logger.isEnabledFor drops the record before any
    # handler is consulted -- which is how the file handler's DEBUG level came to
    # promise a detail level the run log never received. Setting it here, on the root,
    # keeps the console and the run log at one level: a run log that silently diverged
    # from what the operator watched would be worse than either.
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    if args.log_level == "DEBUG":
        # urllib3 logs a line per HTTP connection, and a run makes one per persona
        # attempt; that volume would bury the pre-flight snapshots DEBUG is for.
        logging.getLogger("urllib3").setLevel(logging.INFO)

    axis_ids = [args.model_id, args.strategy_id, args.country_id]
    if args.manifest and any(x is not None for x in axis_ids):
        parser.error("--manifest is mutually exclusive with --model-id, --strategy-id, and --country-id")

    m = None
    _composed_manifest = None

    if args.manifest:
        m = load_manifest(args.manifest)
        logger.info("Loaded manifest: %s", m.name)
        if args.provider is None:
            args.provider = m.provider
        if args.model is None:
            args.model = m.model
        if args.mode is None:
            args.mode = m.mode
        if args.config is None:
            args.config = str(m.config_path)
        if args.strategy is None and m.strategy_path:
            args.strategy = str(m.strategy_path)
        if args.log_llm is None:
            args.log_llm = m.log_llm
        if args.n is None and m.parallel_n is not None:
            args.n = m.parallel_n
        if args.workers is None and m.parallel_workers is not None:
            args.workers = m.parallel_workers
        if args.output_dir is None and m.parallel_output_dir is not None:
            args.output_dir = str(m.parallel_output_dir)
        if args.base_url is None and m.base_url is not None:
            args.base_url = m.base_url
        if args.api_key_env is None and m.api_key_env_var is not None:
            args.api_key_env = m.api_key_env_var
        if not args.retry_until_success and m.retry_until_success:
            args.retry_until_success = m.retry_until_success
        if args.structured_output is None:
            args.structured_output = m.structured_output
    elif args.model_id is not None:
        if args.strategy_id is None or args.country_id is None:
            parser.error("--model-id, --strategy-id, and --country-id must all be provided together")
        m = compose_manifest(args.model_id, args.strategy_id, args.country_id, args.ollama_host)
        # Before any client is constructed and any persona directory is created: a
        # strategy that omits a key the country still requires would generate a full
        # sweep that the validation gate then fails at 0%.
        if m.strategy_path is not None:
            _assert_strategy_covers_country(m.strategy_path, args.strategy_id, args.country_id)
        _composed_manifest = m
        logger.info("Composed manifest: %s", m.name)
        if args.provider is None:
            args.provider = m.provider
        if args.model is None:
            args.model = m.model
        if args.mode is None:
            args.mode = m.mode
        if args.config is None:
            args.config = str(m.config_path)
        if args.strategy is None and m.strategy_path:
            args.strategy = str(m.strategy_path)
        if args.log_llm is None:
            args.log_llm = m.log_llm
        if args.n is None and m.parallel_n is not None:
            args.n = m.parallel_n
        if args.workers is None and m.parallel_workers is not None:
            args.workers = m.parallel_workers
        if args.output_dir is None and m.parallel_output_dir is not None:
            args.output_dir = str(m.parallel_output_dir)
        # Composition set m.base_url from the selected Ollama host; an explicit
        # --base-url is the documented escape hatch and outranks it (this branch
        # only fills the value in when the flag was omitted).
        if args.base_url is None and m.base_url is not None:
            args.base_url = m.base_url
        if args.api_key_env is None and m.api_key_env_var is not None:
            args.api_key_env = m.api_key_env_var
        if not args.retry_until_success and m.retry_until_success:
            args.retry_until_success = m.retry_until_success
        if args.structured_output is None:
            args.structured_output = m.structured_output

    generation_config = m.generation_config if m is not None else {}

    if args.provider is None:
        args.provider = "gemini"
    if args.log_llm is None:
        args.log_llm = True
    if args.workers is None:
        args.workers = 1
    if args.structured_output is None:
        args.structured_output = False

    # Ollama endpoint resolution happens here, in the orchestration layer, and the
    # resolved OllamaHost is reused for the parallelism warning and for provenance
    # below (resolve_host re-reads the registry on every call, so it is resolved
    # once). The axis path already resolved the same host inside compose_manifest;
    # this also covers the --manifest and explicit-CLI paths, where nothing else
    # would supply an endpoint.
    ollama_host = None
    if args.provider == "ollama":
        _resolved_host = ollama_hosts.resolve_host(args.ollama_host)
        if args.base_url is None:
            args.base_url = _resolved_host.base_url
        if args.base_url == _resolved_host.base_url:
            ollama_host = _resolved_host
            logger.info(
                "Ollama host: %s (%s) -> %s",
                _resolved_host.id,
                _resolved_host.label,
                _resolved_host.base_url,
            )
        else:
            # The run is not hitting the registry host, so recording its id would
            # attribute the output to a machine it never touched.
            logger.warning(
                "--base-url %s overrides Ollama host '%s' (%s); this run is not attributed "
                "to any registry host.",
                args.base_url,
                _resolved_host.id,
                _resolved_host.base_url,
            )

    # Ollama-only: prefer the model axis file's per-model VRAM-optimal worker count
    # over whatever --workers was passed (e.g. the GUI's global default). This lets a
    # mixed cloud+local batch keep a single global --workers for cloud combos while each
    # Ollama combo self-tunes to its VRAM ceiling. No-op for cloud providers.
    if args.ollama_auto_workers and args.provider == "ollama":
        if m is not None and m.parallel_workers is not None:
            if args.workers != m.parallel_workers:
                logger.info(
                    "ollama-auto-workers: overriding --workers %d with model axis value %d",
                    args.workers,
                    m.parallel_workers,
                )
            args.workers = m.parallel_workers
        else:
            logger.warning(
                "ollama-auto-workers set but no axis parallel.workers available "
                "(no manifest/axis composed); keeping --workers %d",
                args.workers,
            )

    # Everything that can still refuse this run -- and the log file that will record
    # it -- deliberately precedes the Ollama pre-flight below, which is the first
    # step with a side effect on a machine other people share. Two reasons: a run
    # about to die on a missing --config must not restart someone else's container
    # first, and the pre-flight's own outcome (up to ~2 min of container restart and
    # cold load on the Windows host) is exactly the provenance a later timing
    # analysis needs, so it belongs in the run log rather than the console alone.
    if not args.mode or not args.config:
        parser.error("Either --manifest or both --mode and --config are required")
    if not args.n:
        parser.error("Either --manifest (with parallel.n) or --n is required")
    if not args.output_dir:
        parser.error("Either --manifest (with parallel.output_dir) or --output-dir is required")

    if args.mode == "configurable" and not args.strategy:
        logger.error("--strategy is required for configurable mode")
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    if args.strategy:
        strategy_path = Path(args.strategy)
        if not strategy_path.exists():
            logger.error("Strategy file not found: %s", strategy_path)
            sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if _composed_manifest is not None:
        snapshot_path = output_dir / "manifest_snapshot.yaml"
        snapshot_path.write_text(serialize_manifest(_composed_manifest), encoding="utf-8")
        logger.info("Manifest snapshot written to %s", snapshot_path)

    log_dir = output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    # Deliberately no handler level: --log-level sets the root logger, and a handler
    # level could then only ever subtract from what the operator asked for.
    file_handler.setFormatter(_ElapsedFormatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT))
    logging.getLogger().addHandler(file_handler)
    logger.info("Log file: %s", log_file)

    if args.model:
        model = args.model
    elif args.provider == "gemini":
        model = "gemini-2.5-flash"
    elif args.provider == "ollama":
        model = "llama3.2"
    elif args.provider == "openai_compat":
        model = "mistral-large-latest"
    elif args.provider == "openrouter":
        model = "openai/gpt-4o"
    else:
        model = "sonnet"

    # PROBE -> ACT -> GATE, once per invocation: args.workers is final, ollama_host
    # is bound, `model` is the tag the server will actually be asked for, and no
    # OllamaClient exists yet (each of those probes /api/tags per persona, far too
    # late to gate on). See _ollama_preflight for the decision to mutate a shared host.
    preflight_record = _ollama_preflight(
        ollama_host,
        args.provider,
        model,
        args.workers,
        requested=args.ollama_reconfigure,
    )

    # server_num_parallel is a human-declared value that Ollama exposes on no
    # endpoint, so it can never gate a run -- exceeding it is a throughput
    # disappointment, not an error. A successful pre-flight makes the declared value
    # stale rather than violated, so the warning is suppressed there and only there:
    # 'mismatch', 'failed' and 'no_control_url' all leave the condition standing.
    if (
        ollama_host is not None
        and args.workers > ollama_host.server_num_parallel
        and not _server_parallelism_is_tuned(preflight_record)
    ):
        logger.warning(
            "%d workers exceeds the declared OLLAMA_NUM_PARALLEL=%d of host '%s' (%s): "
            "requests beyond the first %d will queue on the server instead of batching, "
            "so the extra workers buy no throughput. Proceeding -- this is an unverifiable "
            "declared value. Raise OLLAMA_NUM_PARALLEL on that host or lower --workers.",
            args.workers,
            ollama_host.server_num_parallel,
            ollama_host.id,
            ollama_host.label,
            ollama_host.server_num_parallel,
        )

    kwargs = {}
    if args.strategy:
        kwargs["strategy_file"] = str(Path(args.strategy))

    # Resolved once, up front, for two reasons: a malformed strategy graph (cycle or
    # undeclared dependency) then fails before the first LLM call rather than N times
    # inside the workers, and the order every persona was generated in becomes part of
    # the run's provenance. It is a property of the strategy file alone -- identical
    # for every persona and every worker -- so recording it per run is exact, not a
    # sample. Only 'configurable' mode has a category DAG; other modes record null.
    resolved_category_order = resolve_category_order(kwargs["strategy_file"]) if args.strategy else None

    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_metadata = {
        "name": m.name if m is not None else None,
        "manifest": args.manifest,
        "model_config": {
            "provider": args.provider,
            "model": model,
            "base_url": args.base_url,
        },
        "parameters": {
            "mode": args.mode,
            "config": args.config,
            "strategy": args.strategy,
            "log_llm": args.log_llm,
            "n": args.n,
            "workers": args.workers,
            "ollama_auto_workers": args.ollama_auto_workers,
            # Which GPU produced this run. Without it, wall-clock and latency
            # figures from two hosts pool indistinguishably in the
            # generation_metadata analysis and are unrecoverable after the fact.
            # The endpoint itself is recorded above as model_config.base_url.
            "ollama_host": ollama_host.id if ollama_host is not None else None,
            # The three pre-flight facts, each recorded as its own block and each
            # null when it was never established (the pre-flight was not requested,
            # or stopped before that stage). They stay apart because they are
            # independent: 'observed' is the value read back from the server, never
            # the one requested, and a warm-up that failed means persona_00000's
            # wall-clock still carries the cold load this feature exists to move.
            "ollama_reconfigure": preflight_record["reconfigure"],
            "ollama_warm_up": preflight_record["warm_up"],
            "ollama_readiness": preflight_record["readiness"],
            # The evidence behind those three verdicts: {before, after} snapshots of
            # the host, taken by the same probe function either side of the acting.
            # Without them a finished run can say 'already_correct' but not what was
            # already correct, and 'resident_model' -- which model the host actually
            # had loaded, and therefore which one the warm-up evicted -- is
            # recoverable from nothing else after the fact.
            "ollama_server_state": preflight_record["server_state"],
            "output_dir": args.output_dir,
            "force": args.force,
            "retry_until_success": args.retry_until_success,
            "structured_output": args.structured_output,
        },
        # Derived, not requested: the topological order the strategy DAG resolves to.
        # Recorded because 'depends_on' schedules only -- the prompt context block
        # serialises every attribute resolved so far -- so this sequence, not the
        # strategy's edge list, is what each persona's prompts actually saw.
        "resolved_category_order": resolved_category_order,
        "started_at": started_at,
    }
    if _composed_manifest is not None:
        run_metadata["axis_ids"] = {
            "model_id": args.model_id,
            "strategy_id": args.strategy_id,
            "country_id": args.country_id,
        }
    metadata_path = output_dir / "run_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2, ensure_ascii=False)
    logger.info("Run metadata written to %s", metadata_path)

    logger.info("Provider: %s | Mode: %s | Config: %s | Strategy: %s", args.provider, args.mode, args.config, args.strategy)
    logger.info("Model: %s | Generating %d identities with %d workers -> %s", model, args.n, args.workers, output_dir)

    t0 = time.perf_counter()

    pending_indices = list(range(args.n))
    all_results: dict[int, tuple[int, bool, str]] = {}
    round_num = 0

    while pending_indices:
        round_num += 1
        is_retry = round_num > 1

        if is_retry:
            logger.info("--- Retry round %d: %d slot(s) remaining ---", round_num, len(pending_indices))

        round_futures = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for i in pending_indices:
                fut = executor.submit(
                    _generate_one,
                    index=i,
                    total=args.n,
                    mode=args.mode,
                    provider=args.provider,
                    model=model,
                    config_path=str(config_path),
                    output_dir=output_dir,
                    kwargs=kwargs,
                    log_llm=args.log_llm,
                    base_url=args.base_url,
                    api_key_env_var=args.api_key_env,
                    generation_config=generation_config,
                    force=True if is_retry else args.force,
                    retry_until_success=args.retry_until_success,
                    structured_output=args.structured_output,
                )
                round_futures.append(fut)

            for fut in as_completed(round_futures):
                idx, ok, msg = fut.result()
                all_results[idx] = (idx, ok, msg)

        if not args.retry_until_success:
            break

        failed_indices = [idx for idx in pending_indices if not all_results[idx][1]]
        if not failed_indices:
            break

        # Same ceiling as every other retry layer: "until success" must not mean
        # a run that can never end.
        if round_num >= MAX_RETRY_ATTEMPTS:
            logger.error(
                "Retry ceiling reached after %d rounds — %d slot(s) still failing, giving up.",
                round_num, len(failed_indices),
            )
            break

        pending_indices = failed_indices

    results = list(all_results.values())

    elapsed = time.perf_counter() - t0
    ok_count = sum(1 for _, ok, _ in results if ok)
    fail_count = sum(1 for _, ok, _ in results if not ok)

    run_metadata["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    run_metadata["retry_stats"] = {
        "retry_until_success": args.retry_until_success,
        "rounds": round_num,
        "max_rounds": MAX_RETRY_ATTEMPTS if args.retry_until_success else 1,
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(run_metadata, f, indent=2, ensure_ascii=False)

    logger.info("Done in %.1fs. Success: %d, Failed: %d, Output: %s", elapsed, ok_count, fail_count, output_dir)


if __name__ == "__main__":
    main()
