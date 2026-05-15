# Investigate potential issues with SCB02 population generation

**Status:** Pending  
**Branch:** N/A — investigation task

## Context

During comparison runs (seeds 007–013 vs scb02 reference), several anomalies surfaced in the pipeline output that may trace back to how the scb02 reference population itself was generated, not just how the pipeline normalizers work.

## Issues to investigate

- Whether scb02 has any generation artifacts (e.g. unrealistic joint distributions, label encoding quirks, truncated or missing categories) that affect comparison validity
- Whether the `Retired` employment status gap is a scb02 encoding issue (SCB may encode retired as out-of-labor-force under a different label) or a genuine schema mismatch
- Whether the `Business/self-employment` income source appearing as unmapped in B but not A means scb02 uses a different label for the same category
- Whether the birth_country_detail unmapped values (Serbia, Kosovo, Syria, etc.) are genuinely absent from scb02 or encoded differently
- Cross-check scb02 marginal distributions against the live SCB API to verify the reference population is consistent with current Swedish demographics

## Suggested approach

1. Re-fetch a fresh SCB population and compare its marginals against scb02 to detect drift or generation bugs
2. Inspect the scb02 generation metadata/seed to understand what API calls produced it
3. Check if `category_mappings.json` is the source of any label mismatches in the reference side
