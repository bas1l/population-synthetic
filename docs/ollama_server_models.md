# Ollama Hosts — Available Models and Worker Counts

Identity generation with `provider: ollama` can target either of **two** inference hosts. They
are declared in the registry at `config/synthetic/ollama_hosts.yaml`, which is the single
authoritative list of endpoints — no base URL is baked into any `.py` file or model axis file.

| Host id | Label | Endpoint | GPU | `server_num_parallel` |
|---------|-------|----------|-----|-----------------------|
| `linux_3060` *(default)* | Linux server — RTX 3060 12 GB | `http://192.168.0.19:11434` (Docker `ai-stack` network) | NVIDIA RTX 3060, 12 GB | 1 |
| `windows_4070tis` | Windows PC — RTX 4070 Ti SUPER 16 GB | `http://localhost:11434` | NVIDIA RTX 4070 Ti SUPER, 16 GB | 1 |

The **host id** is the only identifier that travels: it is what `--ollama-host` takes, what the
GUI's *Ollama Host* dropdown saves, what keys each model axis file's worker map, and what is
stamped into `run_metadata.json` / `manifest_snapshot.yaml`. It is never a hostname or a URL.

> `server_num_parallel` is the human-declared `OLLAMA_NUM_PARALLEL` of that host's Ollama
> process. It is **not** a worker count and is never used as one — its sole purpose is a warning
> when a resolved worker count exceeds it (requests then queue rather than batch). Ollama exposes
> it on no endpoint, so the code cannot verify it and it must never gate a run.
>
> **Both hosts are currently at `NUM_PARALLEL=1`**, well below every VRAM ceiling below, so any
> run whose worker count exceeds 1 currently logs that warning and queues rather than batches.
> For `linux_3060` this is verifiable out-of-band via `GET http://192.168.0.19:11435/status`
> (the bespoke control API, confirmed 2026-07-27); the parallelism POC stepped that value per
> model via the same API's `/reconfigure`, so it reflects whichever run last touched it. The
> Windows host has no `:11435` equivalent, so its value can only be asserted by hand.

## Model availability and per-host worker counts

A model is served by a host **iff** that host id appears in the model axis file's
`parameters.parallel.workers` map. Absence *is* the unsupported signal — selecting an
unsupported pair raises at composition, before any persona directory is created, naming the
hosts that do serve the model.

| Model axis id | Client tag | `linux_3060` | `windows_4070tis` |
|---------------|------------|--------------|-------------------|
| `ollama_gemma4_e4b` | `gemma4:e4b` | 12 | 84 |
| `ollama_llama32_3b` | `llama3.2:3b-instruct-q4_K_M` | 10 | — |
| `ollama_lucie_7b` | `OpenLLM-France/Lucie-7B-Instruct:latest` | 7 | — |
| `ollama_llama31_8b` | `llama3.1:8b-instruct-q4_K_M` | 6 | 16 |
| `ollama_mistral_nemo_12b` | `mistral-nemo:12b` | 4 | 10 |
| `ollama_qwen3_14b` | `qwen3:14b` | 4 | — |
| `ollama_deepseek_r1_14b` | `deepseek-r1:14b` | 2 | 6 |
| `ollama_gemma2_9b` | `gemma2:9b` | 1 | — |
| `ollama_llama33_70b` | `llama3.3:70b-instruct-q4_K_M` | 1 | — |

The Windows box holds 4 of the 9 modelled weights, digest-identical to the Linux server's copies.

**Provenance of the numbers.** They are not interchangeable — worker capacity is a function of
(model × GPU VRAM), which is exactly why the map is keyed by host:

- `linux_3060` — VRAM-max knees measured in
  [`development/ollama-parallelism-poc/REPORT.md`](development/ollama-parallelism-poc/REPORT.md).
  (That report **supersedes** `RESULTS.md` in the same directory; do not cite the latter.)
  `gemma2:9b` is capped at 1 by its `head_dim=256` KV footprint, not by measurement noise.
- `windows_4070tis` — VRAM-fit ceilings from an external assessment on the RTX 4070 Ti SUPER
  16 GB: the maximum number of slots that fit, with the model spilling to CPU at *NP*+1.

| Model | KV per slot | Slots (NP) | Headroom at NP | Spills at |
|-------|-------------|------------|----------------|-----------|
| `llama3.1:8b-instruct-q4_K_M` | 0.538 GB | 16 | 826 MiB | 17 |
| `mistral-nemo:12b` | 0.640 GB | 10 | 902 MiB | 11 |
| `deepseek-r1:14b` | 0.680 GB | 6 | 1158 MiB | 7 |
| `gemma4:e4b` | 0.051 GB | 84 | 546 MiB | 85 |

Each per-host figure is only *effective* if that host's `OLLAMA_NUM_PARALLEL` is at least as
large; otherwise the extra requests queue at the server.

### Weights on the Linux server outside the model axes

An older inventory snapshot; these have no model axis file and are not selectable through axis
composition. Only one large model fits in VRAM at a time — GPU models unload automatically when
a larger model is requested.

| Model | Size | Client tag | Notes |
|-------|------|------------|-------|
| DeepSeek R1 70B | 42 GB | `deepseek-r1:70b` | CPU inference, reasoning model |
| Qwen 2.5 72B | 47 GB | `qwen2.5:72b-instruct-q4_K_M` | CPU inference, slow |

> `llama3.2:latest` is an alias for `llama3.2:3b-instruct-q4_K_M`. Use the explicit tag to avoid
> ambiguity if more 3.2 variants are added later.

## Selecting a host

```bash
# Explicit host
python scripts/generate/generate_identities_parallel.py \
    --model-id ollama_deepseek_r1_14b --strategy-id all_pick --country-id swedish_02 \
    --ollama-host windows_4070tis --ollama-auto-workers --n 4

# Omitted -> the registry's default_host (linux_3060)
python scripts/generate/generate_identities_parallel.py \
    --model-id ollama_deepseek_r1_14b --strategy-id all_pick --country-id swedish_02 --n 4
```

`--base-url` remains as an explicit escape hatch for an ad-hoc endpoint and **overrides**
`--ollama-host`. When it does, `ollama_host` is recorded as `null` in the provenance rather than
naming a machine that was never contacted.

In the GUI (*Generate → LLM Synthetic Population*), the **Ollama Host** dropdown is populated
from the same registry; switching it updates the Population Summary "Workers" column, which
renders an em dash for a model that host does not serve.

## Adding a host

Config-only, zero `.py` edits:

1. Add an entry under `hosts:` in `config/synthetic/ollama_hosts.yaml`
   (`label`, `base_url`, `gpu`, `server_num_parallel` — all required).
2. Add one key per model axis file whose weights that host holds and whose worker count has been
   assessed for it. Models you omit are simply unsupported there.

The new id appears automatically in `--ollama-host` choices and in the GUI dropdown.

## Using a model in a seed manifest

Set `model_config.model` to the client tag. The frozen
`config/synthetic/manifests/identity_manifest_0NN_*.yaml` seed manifests are historical records
of past runs and still carry their own `base_url`; new work should use the axis path
(`--model-id` / `--strategy-id` / `--country-id`) plus `--ollama-host` instead.

```yaml
model_config:
  provider: "ollama"
  model: "llama3.1:8b-instruct-q4_K_M"
```

## Seed manifest index by model

| Manifests | Model |
|-----------|-------|
| 034–038 | `llama3.3:70b-instruct-q4_K_M` |
| 039–043 | `llama3.2:3b-instruct-q4_K_M` |
| 044–048 | `llama3.1:8b-instruct-q4_K_M` |

## See also

- [`architecture/configuration.md`](architecture/configuration.md) — the registry's config entry.
- [`architecture/axis-composition.md`](architecture/axis-composition.md) — how the worker map
  collapses to a scalar at composition.
- [`development/ollama-parallelism-server-report.md`](development/ollama-parallelism-server-report.md)
  — the `:11435` control API, which exists on the Linux server only.
