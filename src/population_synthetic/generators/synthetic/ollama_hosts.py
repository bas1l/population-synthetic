"""ollama_hosts.py -- The Ollama endpoint registry accessor.

Loads ``config/synthetic/ollama_hosts.yaml`` (the single authoritative list of
Ollama inference endpoints) and resolves a **host id** -- the only identifier that
travels through CLI flags, GUI config, axis-file worker maps and run provenance --
to the endpoint metadata declared for it. No base URL is baked into code: this
module is the one place a URL enters the process, and it comes from config.

Scope (module contract): this module knows about *endpoints* only. It knows
nothing about models, worker counts, axis files, argparse or the GUI -- those
belong to the composition layer (``manifest_loader``) and the orchestration layer
(scripts / GUI) respectively.

Failure policy (fail-fast):

* a missing registry file, malformed YAML, an empty/absent ``hosts`` block, or a
  host entry missing a required key raises, naming the file and the offending key;
* ``default_host`` is validated **at load time**, not at use, so a registry that
  names a non-existent default fails on the first load rather than on the first
  run that omits ``--ollama-host``;
* an unknown host id raises, listing the valid ids -- never a silent fallback to
  the default (a silently wrong GPU is worse than a crash).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from population_synthetic._paths import PROJECT_ROOT

_REGISTRY_PATH = PROJECT_ROOT / "config" / "synthetic" / "ollama_hosts.yaml"

# Every key a host entry must declare (fail-fast if any is absent -- there is no
# default endpoint, no default GPU and no assumed server parallelism).
_REQUIRED_HOST_KEYS = ("label", "base_url", "gpu", "server_num_parallel")


@dataclass(frozen=True)
class OllamaHost:
    """One Ollama inference endpoint, as declared in the registry."""

    id: str
    label: str
    base_url: str
    gpu: str
    # The human-declared ``OLLAMA_NUM_PARALLEL`` of that host's Ollama process.
    # NOT a worker count and never used as one: its sole purpose is letting a
    # caller warn when a resolved worker count exceeds it (requests then queue
    # rather than batch). Ollama exposes this on no endpoint, so it is an
    # unverifiable declared value and must never gate a run.
    server_num_parallel: int


def _load_raw(path: Path) -> dict[str, Any]:
    """Read and minimally validate the registry YAML at *path* (fail-fast)."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Ollama host registry not found: {path}. Expected config/synthetic/ollama_hosts.yaml."
        )

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Ollama host registry must be a mapping, got {type(raw).__name__}: {path}")

    hosts = raw.get("hosts")
    if not isinstance(hosts, dict) or not hosts:
        raise ValueError(
            f"Ollama host registry {path} must declare a non-empty 'hosts' mapping "
            f"(host id -> endpoint metadata), got {hosts!r}."
        )

    default_host = raw.get("default_host")
    if not default_host:
        raise ValueError(f"Ollama host registry missing required top-level key 'default_host': {path}")
    if default_host not in hosts:
        raise ValueError(
            f"Ollama host registry {path} sets default_host {default_host!r}, which is absent from "
            f"'hosts' (declared ids: {list(hosts)})."
        )

    return raw


def _build_host(host_id: str, entry: Any, path: Path) -> OllamaHost:
    """Validate one registry entry and materialize it as an :class:`OllamaHost`."""
    if not isinstance(entry, dict):
        raise ValueError(
            f"Ollama host entry for {host_id!r} must be a mapping, got {type(entry).__name__}: {path}"
        )

    missing = [key for key in _REQUIRED_HOST_KEYS if entry.get(key) is None]
    if missing:
        raise ValueError(f"Ollama host entry for {host_id!r} missing required key(s) {missing}: {path}")

    server_num_parallel = entry["server_num_parallel"]
    if not isinstance(server_num_parallel, int) or isinstance(server_num_parallel, bool) or server_num_parallel < 1:
        raise ValueError(
            f"Ollama host entry for {host_id!r} has non-positive-integer 'server_num_parallel' "
            f"{server_num_parallel!r}: {path}"
        )

    return OllamaHost(
        id=host_id,
        label=str(entry["label"]),
        base_url=str(entry["base_url"]),
        gpu=str(entry["gpu"]),
        server_num_parallel=server_num_parallel,
    )


def load_hosts(path: str | Path | None = None) -> dict[str, OllamaHost]:
    """Load the registry as ``{host_id: OllamaHost}`` (fail-fast).

    *path* defaults to ``config/synthetic/ollama_hosts.yaml`` under the project
    root; it is injectable so tests (and any ad-hoc registry) need no monkeypatching.
    Insertion order follows the YAML document, which is what makes
    :func:`host_ids` stable. Raises :class:`FileNotFoundError` when the file is
    missing and :class:`ValueError` on any malformed shape -- including a
    ``default_host`` that names no declared host.
    """
    registry_path = Path(path) if path is not None else _REGISTRY_PATH
    raw = _load_raw(registry_path)
    return {
        host_id: _build_host(host_id, entry, registry_path)
        for host_id, entry in raw["hosts"].items()
    }


def resolve_host(host_id: str | None = None, path: str | Path | None = None) -> OllamaHost:
    """Return the :class:`OllamaHost` for *host_id*; ``None`` resolves ``default_host``.

    Raises :class:`ValueError` for an unknown id, naming the valid ids -- there is
    no fallback to the default, because dispatching a run to an unintended GPU
    produces normal-looking output attributed to the wrong machine.
    """
    registry_path = Path(path) if path is not None else _REGISTRY_PATH
    raw = _load_raw(registry_path)
    hosts = {hid: _build_host(hid, entry, registry_path) for hid, entry in raw["hosts"].items()}

    resolved_id = raw["default_host"] if host_id is None else host_id
    if resolved_id not in hosts:
        raise ValueError(
            f"Unknown Ollama host id {resolved_id!r}: valid ids are {list(hosts)} "
            f"(declared in {registry_path})."
        )
    return hosts[resolved_id]


def host_ids(path: str | Path | None = None) -> list[str]:
    """Return the declared host ids in registry order.

    The order is the YAML document order and is deliberately stable: it drives the
    argparse ``choices`` listing and the GUI dropdown order.
    """
    return list(load_hosts(path))
