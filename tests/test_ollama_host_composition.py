"""Unit + integration tests for the per-host worker map and its collapse.

``compose_manifest`` is the **one** normalization point where an Ollama model
axis file's ``parameters.parallel.workers`` ``{host_id: n}`` map collapses to the
scalar ``parallel_workers`` every downstream consumer sees, and where the
selected host's ``base_url`` enters the composed config. These tests pin three
things:

1. **The values themselves.** The 9 x 2 table below is the contract: worker
   capacity is a function of (model x GPU VRAM), and a wrong number silently
   over- or under-subscribes a GPU rather than failing. The table is deliberately
   coupled to config and is kept in **one place at the top of this module**, so a
   retune is a one-line edit here.
2. **The availability gate.** A host absent from a model's map raises before any
   persona directory is created, naming the hosts that do serve it.
3. **Inertness elsewhere.** Host resolution lives inside the ``ollama`` branch
   only; a stray ``--ollama-host`` alongside another provider changes nothing.

Temporary axis files used by the malformed-shape tests are written into the real
``config/synthetic/axes/models/`` directory (``compose_manifest`` resolves model
paths from ``PROJECT_ROOT``) with a leading underscore, which ``discover_axis_values``
already skips, and are removed in a fixture teardown.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.generators.synthetic.manifest_loader import (
    _host_worker_map,
    compose_manifest,
    workers_for_host,
)
from population_synthetic.generators.synthetic.ollama_hosts import host_ids, load_hosts

# ---------------------------------------------------------------------------
# THE CONTRACT TABLE -- edit here (and only here) when a host is retuned.
# ---------------------------------------------------------------------------
# ``None`` means "this host does not serve this model": the axis file declares no
# entry for it, which is itself the unsupported signal (there is no second
# availability list to drift out of sync).
#
# linux_3060 (RTX 3060 12 GB) -- VRAM-max knees from
#   docs/development/ollama-parallelism-poc/REPORT.md.
# windows_4070tis (RTX 4070 Ti SUPER 16 GB) -- VRAM-fit ceilings from the
#   external assessment; the model spills to CPU at NP+1. The Windows box holds
#   only 4 of the 9 modelled weights.
UNSUPPORTED = None

EXPECTED_WORKERS: dict[str, dict[str, int | None]] = {
    "ollama_gemma4_e4b":       {"linux_3060": 12, "windows_4070tis": 84},
    "ollama_llama32_3b":       {"linux_3060": 10, "windows_4070tis": UNSUPPORTED},
    "ollama_lucie_7b":         {"linux_3060": 7,  "windows_4070tis": UNSUPPORTED},
    "ollama_llama31_8b":       {"linux_3060": 6,  "windows_4070tis": 16},
    "ollama_mistral_nemo_12b": {"linux_3060": 4,  "windows_4070tis": 10},
    "ollama_qwen3_14b":        {"linux_3060": 4,  "windows_4070tis": UNSUPPORTED},
    "ollama_deepseek_r1_14b":  {"linux_3060": 2,  "windows_4070tis": 6},
    "ollama_gemma2_9b":        {"linux_3060": 1,  "windows_4070tis": UNSUPPORTED},
    "ollama_llama33_70b":      {"linux_3060": 1,  "windows_4070tis": UNSUPPORTED},
}

# Axis co-ordinates that are irrelevant to host resolution but required to compose.
STRATEGY_ID = "all_pick"
COUNTRY_ID = "swedish_02"

MODELS_DIR = PROJECT_ROOT / "config" / "synthetic" / "axes" / "models"

# Every (model, host) cell, flattened for parametrization.
CELLS = [
    (model_id, host_id, expected)
    for model_id, per_host in EXPECTED_WORKERS.items()
    for host_id, expected in per_host.items()
]


def _load_axis(model_id: str) -> dict[str, Any]:
    """Return the parsed model axis file (the shape ``workers_for_host`` consumes)."""
    with open(MODELS_DIR / f"{model_id}.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# The table must stay exhaustive
# ---------------------------------------------------------------------------

def test_table_covers_every_ollama_axis_and_every_host() -> None:
    """Adding an Ollama model or a host forces an explicit entry in the table.

    Without this, a new axis file would silently escape the value assertions
    below and ship with an unverified worker count.
    """
    on_disk = {p.stem for p in MODELS_DIR.glob("ollama_*.yaml")}
    assert on_disk == set(EXPECTED_WORKERS)

    registered = host_ids()
    for model_id, per_host in EXPECTED_WORKERS.items():
        assert list(per_host) == registered, f"{model_id} table row is missing a host"


def test_every_axis_worker_key_is_a_registered_host_id() -> None:
    """No axis file may key its worker map on a host absent from the registry.

    Edge case from the plan: a typo'd or retired host id in an axis file makes
    that (host, model) pair permanently unreachable. Composition itself cannot see
    a *stray* key -- it only checks that the selected host is present -- so the
    cross-check lives here, where it fails at test time rather than at run time.
    """
    registered = set(host_ids())
    for model_id in EXPECTED_WORKERS:
        declared = set(_host_worker_map(_load_axis(model_id)))
        unknown = declared - registered
        assert not unknown, f"{model_id} declares unregistered host id(s): {sorted(unknown)}"


# ---------------------------------------------------------------------------
# Table-driven collapse: 9 axes x both hosts, supported and unsupported cells
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("model_id", "host_id", "expected"),
    CELLS,
    ids=[f"{m}-{h}" for m, h, _ in CELLS],
)
def test_compose_collapses_worker_map_to_expected_scalar(
    model_id: str, host_id: str, expected: int | None
) -> None:
    """Each cell either collapses to its declared int or raises the availability gate."""
    if expected is UNSUPPORTED:
        with pytest.raises(ValueError, match="does not serve model") as excinfo:
            compose_manifest(model_id, STRATEGY_ID, COUNTRY_ID, host_id)
        message = str(excinfo.value)
        assert model_id in message
        assert host_id in message
        # The message must name the hosts that DO serve it, so the user's next
        # action is obvious without opening the axis file.
        supported = [h for h, n in EXPECTED_WORKERS[model_id].items() if n is not UNSUPPORTED]
        for host in supported:
            assert host in message
        return

    config = compose_manifest(model_id, STRATEGY_ID, COUNTRY_ID, host_id)
    assert config.parallel_workers == expected
    # A scalar, never the map: nothing below this layer learns that hosts exist.
    assert isinstance(config.parallel_workers, int)
    assert config.ollama_host == host_id
    assert config.base_url == load_hosts()[host_id].base_url


@pytest.mark.parametrize(
    ("model_id", "host_id", "expected"),
    CELLS,
    ids=[f"{m}-{h}" for m, h, _ in CELLS],
)
def test_workers_for_host_matches_the_table_without_raising(
    model_id: str, host_id: str, expected: int | None
) -> None:
    """The non-raising twin agrees with the gate on every cell.

    The GUI summary panel must *display* an unsupported pair (as an em dash),
    not crash on it, so this returns ``None`` where composition raises.
    """
    assert workers_for_host(_load_axis(model_id), host_id) == expected


def test_omitted_host_resolves_the_registry_default() -> None:
    """``ollama_host_id=None`` composes against ``default_host``, and records it.

    Provenance names the machine that actually ran, not "unspecified".
    """
    config = compose_manifest("ollama_deepseek_r1_14b", STRATEGY_ID, COUNTRY_ID, None)
    default = load_hosts()["linux_3060"]
    assert config.ollama_host == default.id
    assert config.base_url == default.base_url
    assert config.parallel_workers == EXPECTED_WORKERS["ollama_deepseek_r1_14b"]["linux_3060"]


# ---------------------------------------------------------------------------
# Integration: the two cases named in the plan
# ---------------------------------------------------------------------------

def test_deepseek_against_windows_host_yields_local_url_and_scalar_workers() -> None:
    """The headline supported pair: local endpoint, scalar worker count."""
    config = compose_manifest(
        "ollama_deepseek_r1_14b", STRATEGY_ID, COUNTRY_ID, ollama_host_id="windows_4070tis"
    )
    assert config.base_url == "http://localhost:11434"
    assert config.ollama_host == "windows_4070tis"
    assert isinstance(config.parallel_workers, int)
    assert config.parallel_workers == 6


def test_llama33_70b_against_windows_host_raises_naming_the_supporting_host() -> None:
    """The headline unsupported pair fails at composition, before any I/O."""
    with pytest.raises(ValueError) as excinfo:
        compose_manifest(
            "ollama_llama33_70b", STRATEGY_ID, COUNTRY_ID, ollama_host_id="windows_4070tis"
        )
    message = str(excinfo.value)
    assert "ollama_llama33_70b" in message
    assert "linux_3060" in message


# ---------------------------------------------------------------------------
# Malformed / legacy axis shapes
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_axis_file():
    """Write a throwaway ``_``-prefixed model axis file; remove it on teardown.

    ``compose_manifest`` resolves the model path from ``PROJECT_ROOT``, so the file
    must live in the real axis directory. The underscore prefix keeps it out of
    ``discover_axis_values`` (and therefore out of every GUI listing) even if a
    teardown is ever missed.
    """
    written: list = []

    def _write(model_id: str, workers: Any) -> str:
        doc = {
            "id": model_id,
            "label": "Throwaway test axis",
            "model_config": {
                "provider": "ollama",
                "model": "test:0b",
                "generation_config": {"temperature": 0.7},
            },
            "parameters": {"parallel": {"workers": workers}},
        }
        path = MODELS_DIR / f"{model_id}.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        written.append(path)
        return model_id

    yield _write

    for path in written:
        path.unlink(missing_ok=True)


def test_compose_raises_on_legacy_scalar_workers(temp_axis_file) -> None:
    """The pre-registry scalar shape is a hard error, not a compatible widening.

    Accepting it would silently reintroduce a host-implicit worker count -- the
    exact bug the per-host map removes.
    """
    model_id = temp_axis_file("_pytest_ollama_scalar_workers", 4)
    with pytest.raises(ValueError, match="must be a .*mapping") as excinfo:
        compose_manifest(model_id, STRATEGY_ID, COUNTRY_ID, "linux_3060")
    message = str(excinfo.value)
    assert model_id in message
    assert "ollama_hosts.yaml" in message


def test_workers_for_host_still_raises_on_a_malformed_shape() -> None:
    """A bad ``workers`` shape is a config error, not an unsupported pair.

    ``workers_for_host`` softens only the *absent host* case; it must not swallow
    a scalar into a ``None`` the GUI would render as an em dash.
    """
    model_data = {"id": "fake", "parameters": {"parallel": {"workers": 4}}}
    with pytest.raises(ValueError, match="must be a .*mapping"):
        workers_for_host(model_data, "linux_3060")


def test_axis_file_declaring_only_unregistered_hosts_raises_at_composition(
    temp_axis_file,
) -> None:
    """An axis whose only worker keys are unregistered serves no selectable host."""
    model_id = temp_axis_file("_pytest_ollama_ghost_host", {"ghost_host": 3})
    for host_id in host_ids():
        with pytest.raises(ValueError, match="does not serve model") as excinfo:
            compose_manifest(model_id, STRATEGY_ID, COUNTRY_ID, host_id)
        assert "ghost_host" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Inertness for non-Ollama providers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "model_id",
    ["claude_sonnet", "gemini_flash", "openrouter_gpt55"],
)
def test_ollama_host_is_inert_for_other_providers(model_id: str) -> None:
    """Host resolution happens only inside the ``ollama`` branch.

    A stray ``--ollama-host`` alongside another provider must change nothing:
    no host recorded, no base URL injected, and the axis file's own scalar
    ``workers`` preserved.
    """
    baseline = compose_manifest(model_id, STRATEGY_ID, COUNTRY_ID)
    with_host = compose_manifest(
        model_id, STRATEGY_ID, COUNTRY_ID, ollama_host_id="windows_4070tis"
    )

    assert with_host.ollama_host is None
    assert with_host.base_url == baseline.base_url
    assert with_host.parallel_workers == baseline.parallel_workers
    assert baseline.provider != "ollama"


def test_unregistered_host_id_is_not_even_resolved_for_other_providers() -> None:
    """Inertness holds for a host id that would raise if it were resolved."""
    config = compose_manifest(
        "claude_sonnet", STRATEGY_ID, COUNTRY_ID, ollama_host_id="no_such_host"
    )
    assert config.ollama_host is None
