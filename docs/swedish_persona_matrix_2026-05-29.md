# Swedish Synthetic Population — Persona Matrix

**Snapshot date:** 2026-05-29 (Thursday)
**Output base:** `F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data/01_Raw/`

## Model × Strategy Cross-Tabulation

Cells show **completed identities / total persona directories**.

| Model | all_pick | all_pick_dag | all_generate_pick | all_generate_evaluate_pick | all_generate_evaluate_random_pick |
|---|---|---|---|---|---|
| claude_haiku | 100/100 | 100/100 | 31/31 | — | — |
| ollama_gemma4_e4b | 100/100 | 100/100 | 100/100 | 100/100 | 100/100 |
| ollama_llama31_8b | 100/100 | 100/100 | 100/100 | 100/100 | 100/100 |
| ollama_mistral_nemo_12b | 100/100 | 100/100 | 100/100 | 100/100 | 100/100 |
| ollama_lucie_7b | 16/100 | — | — | — | — |
| ollama_qwen3_14b | 100/100 | — | — | 1/1 | — |
| ollama_deepseek_r1_14b | — | — | — | 3/5 | — |
| ollama_llama33_70b | — | — | — | — | 0/0 |

## Summary

- **Total completed identities:** 1,802 across 22 runs
- **Full coverage (all 5 strategies, 100 each):** ollama_gemma4_e4b, ollama_llama31_8b, ollama_mistral_nemo_12b
- **Partial coverage:** claude_haiku (3 strategies), ollama_qwen3_14b (1 full + 1 started), ollama_lucie_7b (16/100 — high failure rate), ollama_deepseek_r1_14b (3/5)
- **Not started:** ollama_llama33_70b (directory exists, 0 personas)
- **No runs at all:** claude_opus, claude_sonnet, gemini_flash, ollama_gemma2_9b, ollama_llama32_3b
