"""Unit tests for the Ollama endpoint registry accessor.

Covers :mod:`population_synthetic.generators.synthetic.ollama_hosts` — the one
place a base URL enters the process. Two properties are under test:

1. **Fail-fast loading.** Every malformed registry shape raises rather than
   yielding a partially-valid host table. A silently wrong endpoint dispatches a
   whole sweep to the wrong GPU and produces normal-looking output attributed to
   the wrong machine, so a crash is strictly the better outcome.
2. **Stable ordering.** :func:`host_ids` order drives the argparse ``choices``
   listing and the GUI dropdown order, so it must follow the YAML document
   rather than a set/hash iteration.

Malformed registries are written to ``tmp_path`` and passed via the injectable
``path`` argument — no monkeypatching of module state, and the real registry is
never mutated. The real registry is asserted against separately, because its
contents are themselves part of the contract (the CLI ``choices`` list).
"""

from __future__ import annotations

import pytest
import yaml

from population_synthetic._paths import PROJECT_ROOT
from population_synthetic.generators.synthetic.ollama_hosts import (
    OllamaHost,
    host_ids,
    load_hosts,
    resolve_host,
)

# The shipped registry. Its ids are a public contract: they appear in
# ``--ollama-host`` choices, in the GUI flow YAML and in run provenance.
REAL_REGISTRY = PROJECT_ROOT / "config" / "synthetic" / "ollama_hosts.yaml"
REAL_HOST_IDS = ["linux_3060", "windows_4070tis"]
REAL_DEFAULT_HOST = "linux_3060"

# A minimal well-formed registry, written per-test with one field perturbed.
_VALID_REGISTRY = """\
default_host: alpha
hosts:
  alpha:
    label: "Alpha box"
    base_url: "http://alpha.invalid:11434"
    gpu: "GPU A"
    server_num_parallel: 4
  beta:
    label: "Beta box"
    base_url: "http://beta.invalid:11434"
    gpu: "GPU B"
    server_num_parallel: 1
"""


def _write(tmp_path, text: str, name: str = "hosts.yaml"):
    """Write *text* as a registry file under *tmp_path* and return its path."""
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# load_hosts -- happy path
# ---------------------------------------------------------------------------

def test_load_hosts_materializes_frozen_host_objects(tmp_path) -> None:
    """A well-formed registry yields one frozen OllamaHost per declared id."""
    hosts = load_hosts(_write(tmp_path, _VALID_REGISTRY))

    assert list(hosts) == ["alpha", "beta"]
    alpha = hosts["alpha"]
    assert isinstance(alpha, OllamaHost)
    assert alpha.id == "alpha"
    assert alpha.label == "Alpha box"
    assert alpha.base_url == "http://alpha.invalid:11434"
    assert alpha.gpu == "GPU A"
    assert alpha.server_num_parallel == 4

    # Frozen: a host is a value object, so no caller can retarget an endpoint.
    with pytest.raises(Exception):
        alpha.base_url = "http://elsewhere.invalid"  # type: ignore[misc]


def test_load_hosts_reads_the_real_registry() -> None:
    """The shipped registry loads and declares exactly the two documented hosts."""
    hosts = load_hosts()
    assert list(hosts) == REAL_HOST_IDS
    assert hosts["linux_3060"].base_url == "http://192.168.0.19:11434"
    assert hosts["windows_4070tis"].base_url == "http://localhost:11434"


# ---------------------------------------------------------------------------
# load_hosts -- fail-fast on every malformed shape
# ---------------------------------------------------------------------------

def test_load_hosts_missing_file_raises(tmp_path) -> None:
    """An absent registry raises FileNotFoundError naming the expected path."""
    missing = tmp_path / "not_here.yaml"
    with pytest.raises(FileNotFoundError, match="ollama_hosts.yaml"):
        load_hosts(missing)


def test_load_hosts_malformed_yaml_raises(tmp_path) -> None:
    """Unparseable YAML surfaces the parser error rather than an empty table."""
    path = _write(tmp_path, "hosts: [unclosed\n  - :::\n")
    with pytest.raises(yaml.YAMLError):
        load_hosts(path)


def test_load_hosts_non_mapping_root_raises(tmp_path) -> None:
    """A registry whose root is not a mapping raises, naming the actual type."""
    path = _write(tmp_path, "just a bare string\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_hosts(path)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("default_host: alpha\nhosts: {}\n", id="empty-hosts"),
        pytest.param("default_host: alpha\nhosts:\n", id="null-hosts"),
        pytest.param("default_host: alpha\n", id="absent-hosts"),
    ],
)
def test_load_hosts_empty_hosts_block_raises(tmp_path, body: str) -> None:
    """An empty/absent ``hosts`` block raises and names the offending file."""
    path = _write(tmp_path, body)
    with pytest.raises(ValueError, match="non-empty 'hosts' mapping") as excinfo:
        load_hosts(path)
    assert str(path) in str(excinfo.value)


def test_load_hosts_absent_default_host_raises(tmp_path) -> None:
    """A registry with no ``default_host`` raises: there is no implicit default."""
    body = _VALID_REGISTRY.replace("default_host: alpha\n", "")
    with pytest.raises(ValueError, match="default_host"):
        load_hosts(_write(tmp_path, body))


def test_load_hosts_default_host_naming_absent_host_raises_at_load(tmp_path) -> None:
    """``default_host`` is validated at load, not deferred to the first use.

    Edge case from the plan: a registry naming a non-existent default must fail on
    the first load, not on the first run that happens to omit ``--ollama-host``.
    """
    body = _VALID_REGISTRY.replace("default_host: alpha", "default_host: gamma")
    with pytest.raises(ValueError, match="default_host") as excinfo:
        load_hosts(_write(tmp_path, body))
    message = str(excinfo.value)
    assert "gamma" in message
    # The message must show what *is* declared so the typo is obvious.
    assert "alpha" in message and "beta" in message


def test_load_hosts_non_mapping_host_entry_raises(tmp_path) -> None:
    """A scalar where a host entry belongs raises, naming the host id."""
    body = "default_host: alpha\nhosts:\n  alpha: \"http://alpha.invalid:11434\"\n"
    with pytest.raises(ValueError, match="'alpha' must be a mapping"):
        load_hosts(_write(tmp_path, body))


@pytest.mark.parametrize("key", ["label", "base_url", "gpu", "server_num_parallel"])
def test_load_hosts_missing_required_key_raises(tmp_path, key: str) -> None:
    """Every required host key is mandatory; the message names the missing one."""
    data = yaml.safe_load(_VALID_REGISTRY)
    del data["hosts"]["alpha"][key]
    path = _write(tmp_path, yaml.safe_dump(data))
    with pytest.raises(ValueError, match="missing required key") as excinfo:
        load_hosts(path)
    assert key in str(excinfo.value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param("4", id="string"),
        pytest.param(2.5, id="float"),
        pytest.param(True, id="bool"),
    ],
)
def test_load_hosts_rejects_non_positive_int_server_num_parallel(tmp_path, value) -> None:
    """``server_num_parallel`` must be a positive int -- it is a warning threshold.

    A bool is rejected explicitly: ``True == 1`` in Python, so an unguarded
    ``isinstance(x, int)`` would accept ``server_num_parallel: yes`` as one slot.
    """
    data = yaml.safe_load(_VALID_REGISTRY)
    data["hosts"]["alpha"]["server_num_parallel"] = value
    path = _write(tmp_path, yaml.safe_dump(data))
    with pytest.raises(ValueError, match="server_num_parallel"):
        load_hosts(path)


# ---------------------------------------------------------------------------
# resolve_host
# ---------------------------------------------------------------------------

def test_resolve_host_none_returns_default_host(tmp_path) -> None:
    """``None`` resolves the registry's declared ``default_host``."""
    host = resolve_host(None, _write(tmp_path, _VALID_REGISTRY))
    assert host.id == "alpha"
    assert host.base_url == "http://alpha.invalid:11434"


def test_resolve_host_none_on_real_registry() -> None:
    """On the shipped registry, an omitted ``--ollama-host`` targets the Linux box."""
    assert resolve_host(None).id == REAL_DEFAULT_HOST


def test_resolve_host_explicit_id(tmp_path) -> None:
    """An explicit id returns that host, not the default."""
    host = resolve_host("beta", _write(tmp_path, _VALID_REGISTRY))
    assert host.id == "beta"
    assert host.server_num_parallel == 1


def test_resolve_host_unknown_id_raises_listing_valid_ids(tmp_path) -> None:
    """An unknown id raises and lists every valid id -- never a silent default."""
    path = _write(tmp_path, _VALID_REGISTRY)
    with pytest.raises(ValueError, match="Unknown Ollama host id") as excinfo:
        resolve_host("nope", path)
    message = str(excinfo.value)
    assert "nope" in message
    assert "alpha" in message and "beta" in message


def test_resolve_host_unknown_id_on_real_registry_lists_both_hosts() -> None:
    """The shipped registry's error message names both real host ids."""
    with pytest.raises(ValueError, match="Unknown Ollama host id") as excinfo:
        resolve_host("nope")
    message = str(excinfo.value)
    for host_id in REAL_HOST_IDS:
        assert host_id in message


# ---------------------------------------------------------------------------
# host_ids -- ordering is a contract
# ---------------------------------------------------------------------------

def test_host_ids_follows_yaml_document_order(tmp_path) -> None:
    """Order is the YAML document order, not sorted and not hash order."""
    body = _VALID_REGISTRY.replace("default_host: alpha", "default_host: beta")
    # Reverse the declaration order; the accessor must follow the file.
    reversed_body = (
        "default_host: beta\nhosts:\n"
        '  zeta:\n    label: "Z"\n    base_url: "http://z.invalid"\n'
        '    gpu: "GPU Z"\n    server_num_parallel: 1\n'
        '  beta:\n    label: "B"\n    base_url: "http://b.invalid"\n'
        '    gpu: "GPU B"\n    server_num_parallel: 1\n'
    )
    assert host_ids(_write(tmp_path, reversed_body)) == ["zeta", "beta"]
    assert host_ids(_write(tmp_path, body, name="ordered.yaml")) == ["alpha", "beta"]


def test_host_ids_on_real_registry_is_stable() -> None:
    """The shipped ids, in file order -- this list is the argparse ``choices``."""
    assert host_ids() == REAL_HOST_IDS
    # Repeated calls must not reorder (no caching, but also no set round-trip).
    assert host_ids() == host_ids()
