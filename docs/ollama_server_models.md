# Ollama Server — Available Models

**Server:** `http://192.168.0.19:11434` (secondary Linux server, Docker `ai-stack` network)

Only one model can be loaded in VRAM at a time. GPU models unload automatically when a larger model is requested.

| Model | Size | Client tag | Notes |
|-------|------|------------|-------|
| Llama 3.2 3B | 2.0 GB | `llama3.2:3b-instruct-q4_K_M` | Fast, lightweight; fits entirely in VRAM |
| Llama 3.1 8B | 4.9 GB | `llama3.1:8b-instruct-q4_K_M` | Best GPU-only model |
| Llama 3.3 70B | 42 GB | `llama3.3:70b-instruct-q4_K_M` | CPU inference, slow |
| DeepSeek R1 70B | 42 GB | `deepseek-r1:70b` | CPU inference, reasoning model |
| Qwen 2.5 72B | 47 GB | `qwen2.5:72b-instruct-q4_K_M` | CPU inference, slow |

> `llama3.2:latest` is an alias for `llama3.2:3b-instruct-q4_K_M`. Use the explicit tag to avoid ambiguity if more 3.2 variants are added later.

## Using a model in a seed manifest

Set `model_config.model` to the client tag:

```yaml
model_config:
  provider: "ollama"
  model: "llama3.1:8b-instruct-q4_K_M"
  base_url: "http://192.168.0.19:11434"
```

## Seed manifest index by model

| Manifests | Model |
|-----------|-------|
| 034–038 | `llama3.3:70b-instruct-q4_K_M` |
| 039–043 | `llama3.2:3b-instruct-q4_K_M` |
| 044–048 | `llama3.1:8b-instruct-q4_K_M` |
