"""The worked example for Figure 3B: employment status, read from the run telemetry.

One model (Claude Sonnet), the first individual (persona_00000) of each strategy's swedish_02 run, no
selection. Values are the raw LLM text as returned (before mapping), so capitalisation and language vary
exactly as in the data. Asserted, so a redraw fails if the raw files change.
"""
from __future__ import annotations

import json
from pathlib import Path

from common import STRATEGIES, _OUT

MODEL = "claude_sonnet"
PERSONA = "persona_00000"
ATTRIBUTE = "employment_status"
RAW = Path(_OUT) / "01_Raw"


def _calls(strategy):
    d = RAW / f"swedish_02_{strategy}_{MODEL}" / PERSONA
    rows = [json.loads(line) for line in (d / "llm_interactions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]
    rows = [r for r in rows if r["category"] == ATTRIBUTE and r.get("error") in (None, "None")]
    value = json.loads((d / "identity.json").read_text(encoding="utf-8"))[ATTRIBUTE]
    return rows, value


EX = {}
for s in STRATEGIES:
    rows, value = _calls(s)
    steps = {r["step"]: r for r in rows}
    e = {"value": value, "n_calls": len(rows)}
    if "enumerate" in steps:
        e["candidates"] = json.loads(steps["enumerate"]["raw_response"])["candidates"]
    if "evaluate" in steps:
        e["weights"] = json.loads(steps["evaluate"]["raw_response"])["weights"]
        assert len(e["weights"]) == len(e["candidates"])
    e["context_lines"] = [ln for ln in rows[0]["prompt"].split("\n")[1:] if ": " in ln and not ln.startswith("Given")] \
        if rows[0]["prompt"].startswith("Context:") else []
    EX[s] = e

A, B, C, D, E = STRATEGIES
assert EX[A]["value"] == "Förvärvsarbetande (anställd)" and EX[A]["n_calls"] == 1
assert EX[B]["value"] == "employed full-time" and EX[B]["n_calls"] == 1
assert EX[C]["value"] == "Employed full-time" and EX[C]["candidates"][:4] == [
    "Employed full-time", "Employed part-time", "Self-employed", "Parental leave"]
assert EX[D]["value"] == "Employed full-time" and EX[D]["candidates"][:4] == [
    "Employed full-time", "Employed part-time", "Self-employed", "Unemployed"]
assert EX[D]["weights"][:4] == [0.68, 0.08, 0.07, 0.06]
assert EX[E]["value"] == "unemployed" and EX[E]["candidates"][:4] == [
    "employed full-time", "employed part-time", "self-employed", "unemployed"]
assert EX[E]["weights"][:4] == [0.68, 0.06, 0.1, 0.04]
assert EX[E]["n_calls"] == 2  # enumerate + evaluate; the draw is code
N_SHOWN = 4

if __name__ == "__main__":
    for s in STRATEGIES:
        print(s, {k: v for k, v in EX[s].items() if k != "context_lines"})
        print("   context:", EX[s]["context_lines"])
