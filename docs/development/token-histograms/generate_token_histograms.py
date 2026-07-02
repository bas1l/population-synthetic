"""Per-call input/output token histograms for Swedish runs, per method x model.

Goal: characterise the *distribution* of per-call input/output tokens (the doc only
has per-strategy sums) so we can read off the maximum context size each model saw.

Token source per model (mirrors swedish-token-usage-by-model.md):
  - Ollama models  -> REAL per-call prompt_tokens/completion_tokens from logs/run_*.log
  - Claude models  -> tiktoken cl100k_base proxy over each call's prompt / raw_response
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import tiktoken

RAW = Path("F:/liu-onedrive-nospecial-carac/_Teams/Gauss/02_Data/01_Raw")
OUT = Path(__file__).resolve().parent  # write figures + summary next to this script
OUT.mkdir(parents=True, exist_ok=True)

# Known methods, longest-first so 'all_pick_dag' wins over 'all_pick'.
METHODS = [
    "all_generate_evaluate_random_pick",
    "all_generate_evaluate_pick",
    "all_generate_pick",
    "all_pick_dag",
    "all_pick",
]
METHOD_ORDER = ["all_pick", "all_pick_dag", "all_generate_pick",
                "all_generate_evaluate_pick", "all_generate_evaluate_random_pick"]

ENC = tiktoken.get_encoding("cl100k_base")

_LOG_CALL = re.compile(
    r"(?:ollama|openai_compat) call:.*?prompt_tokens=(\S+)\s+completion_tokens=(\S+)"
)


def split_dir(name: str) -> tuple[str, str] | None:
    if not name.startswith("swedish_"):
        return None
    rest = name[len("swedish_"):]
    for m in METHODS:
        if rest.startswith(m + "_"):
            return m, rest[len(m) + 1:]
    return None


def real_tokens_from_logs(run_dir: Path) -> tuple[list[int], list[int]]:
    """Every logged prompt/completion token count (Ollama). Empty for Claude."""
    ins: list[int] = []
    outs: list[int] = []
    logs = run_dir / "logs"
    if not logs.is_dir():
        return ins, outs
    for lf in sorted(logs.glob("run_*.log")):
        for line in lf.open(encoding="utf-8", errors="replace"):
            mm = _LOG_CALL.search(line)
            if not mm:
                continue
            pt, ct = mm.group(1), mm.group(2)
            if pt.lower() != "none":
                try:
                    ins.append(int(pt))
                except ValueError:
                    pass
            if ct.lower() != "none":
                try:
                    outs.append(int(ct))
                except ValueError:
                    pass
    return ins, outs


def est_tokens_from_jsonl(run_dir: Path) -> tuple[list[int], list[int]]:
    """tiktoken counts over every call's prompt (input) and raw_response (output)."""
    ins: list[int] = []
    outs: list[int] = []
    for pdir in sorted(run_dir.glob("persona_*")):
        f = pdir / "llm_interactions.jsonl"
        if not f.exists():
            f2 = pdir / "llm_interactions.json"
            if not f2.exists():
                continue
            f = f2
        text = f.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        records = json.loads(text) if text[0] == "[" else [
            json.loads(ln) for ln in text.splitlines() if ln.strip()
        ]
        for r in records:
            ins.append(len(ENC.encode(r.get("prompt") or "")))
            outs.append(len(ENC.encode(r.get("raw_response") or "")))
    return ins, outs


def stats(vals: list[int]) -> dict:
    a = np.asarray(vals)
    return {
        "n": int(a.size),
        "max": int(a.max()),
        "p99": int(np.percentile(a, 99)),
        "p95": int(np.percentile(a, 95)),
        "median": int(np.percentile(a, 50)),
        "mean": round(float(a.mean()), 1),
    }


# ---- collect ----------------------------------------------------------------
data: dict[str, dict[str, dict]] = {}  # model -> method -> {source,in,out}
for d in sorted(RAW.glob("swedish_*")):
    if not d.is_dir():
        continue
    sm = split_dir(d.name)
    if sm is None:
        continue
    method, model = sm
    real_in, real_out = real_tokens_from_logs(d)
    if real_in:  # Ollama: real token counts logged
        src, tin, tout = "REAL", real_in, real_out
    else:        # Claude: tiktoken proxy
        est_in, est_out = est_tokens_from_jsonl(d)
        src, tin, tout = "EST", est_in, est_out
    if not tin:
        print(f"  !! no data: {d.name}")
        continue
    data.setdefault(model, {})[method] = {"source": src, "in": tin, "out": tout}
    print(f"{model:26s} {method:34s} {src:4s} calls_in={len(tin):5d} "
          f"max_in={max(tin):6d} max_out={max(tout):6d}")

# ---- figures: one per model, rows=methods, cols=[input, output] -------------
for model, methods in sorted(data.items()):
    present = [m for m in METHOD_ORDER if m in methods]
    nrows = len(present)
    fig, axes = plt.subplots(nrows, 2, figsize=(13, 2.6 * nrows), squeeze=False)
    src_label = methods[present[0]]["source"]
    src_txt = "REAL tokens (logs)" if src_label == "REAL" else "tiktoken cl100k_base estimate"
    fig.suptitle(f"Swedish — {model}   [{src_txt}]", fontsize=14, y=0.995)
    for row, method in enumerate(present):
        rec = methods[method]
        for col, (key, color, lab) in enumerate(
            [("in", "#3b6ea5", "input"), ("out", "#b5651d", "output")]
        ):
            ax = axes[row][col]
            vals = rec[key]
            ax.hist(vals, bins=50, color=color, alpha=0.85)
            st = stats(vals)
            ax.axvline(st["max"], color="red", ls="--", lw=1)
            ax.set_title(f"{method} — {lab} tokens", fontsize=9)
            ax.text(0.97, 0.95,
                    f"n={st['n']}\nmax={st['max']}\np95={st['p95']}\nmed={st['median']}",
                    transform=ax.transAxes, ha="right", va="top", fontsize=8,
                    bbox=dict(boxstyle="round", fc="white", ec="0.7", alpha=0.85))
            ax.tick_params(labelsize=7)
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    out = OUT / f"tokens_{model}.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  wrote {out}")

# ---- summary table ----------------------------------------------------------
lines = ["| Model | Method | Src | Calls | Max in | p95 in | Med in | Max out | p95 out | Med out |",
         "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
for model in sorted(data):
    for method in METHOD_ORDER:
        if method not in data[model]:
            continue
        rec = data[model][method]
        si, so = stats(rec["in"]), stats(rec["out"])
        lines.append(f"| {model} | {method} | {rec['source']} | {si['n']} | "
                     f"{si['max']} | {si['p95']} | {si['median']} | "
                     f"{so['max']} | {so['p95']} | {so['median']} |")
table = "\n".join(lines)
(OUT / "summary.md").write_text(table, encoding="utf-8")
print("\n" + table)
