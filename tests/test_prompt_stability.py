"""Every prompt every strategy renders, pinned by hash against pre-refactor output.

The benchmark's results are only comparable across runs made months apart if the
prompt text is the same in both. A refactor that quietly reworded one clause would
not fail any behavioural test -- it would just make old and new fidelity scores
incomparable, silently and irreversibly.

So this test replays each strategy YAML end to end against a canned call seam and
hashes the whole stream of ``(category, method, step, prompt)`` tuples. The
expected digests were captured from the implementation as it stood *before* the
``Category``/``Persona`` refactor.

**If this fails**, the question is which side moved:

* changed ``src/`` and did not intend to change prompts -> the refactor drifted; fix
  the code, not the digest;
* deliberately reworded a prompt, or added/removed/reordered a category in a
  strategy YAML -> the digest is stale. Re-capture it, and record in the run
  metadata that results either side of the change are not poolable.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import pytest
import yaml

from population_synthetic.generators.synthetic.identity_generator_configurable import (
    IdentityGeneratorConfigurable,
)
from population_synthetic.generators.synthetic.resolution_context import ResolutionContext

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STRATEGY_DIR = _REPO_ROOT / "config" / "synthetic" / "axes" / "strategies"

# Co-located in the strategies directory but not a strategy: no ``categories`` block.
_NON_STRATEGY_FILES = ("_families.yaml",)

_MARKER = "__VAL"

# sha256 over ``json.dumps([[category, method, step, prompt], ...])`` for one full
# run of each strategy under the canned seam below. Captured pre-refactor.
EXPECTED_DIGESTS = {
    "_compared_only_generate_evaluate_random_pick.yaml":
        "46d665ad50bf11cbbde950579ab299b032d19f7754c2259f34b944c515ab695e",
    "_debug_minimal.yaml":
        "0e616b7ae1bde62a0dafb6d794d09f9714973baf7d059f40e076bb0720150d1e",
    "all_generate_evaluate_pick.yaml":
        "6e6123e1b6f042258677cb4d69ad1c5fb2da94aabdfa257641346da9d7889ae2",
    "all_generate_evaluate_pick_v2.yaml":
        "ab03f9861884fec8a0ba26e561d6a504a17664b1865f3b117ca02d8540e818c4",
    "all_generate_evaluate_random_pick.yaml":
        "cac39068137df54a70c61ff10c549f134d4f6d8ce7d23dc09640368f619a24be",
    "all_generate_evaluate_random_pick_v2.yaml":
        "252eaaec1c4d09ffdfacbb693a63c5b3be304c28a83ed97a967e875f1b38dd19",
    "all_generate_pick.yaml":
        "c735cb88f52cd99cdf44dff631593baf8c9b810254f4ab9eb8ee47ecdb901e14",
    "all_generate_pick_v2.yaml":
        "75125d269b515d36840afa9483c4b11c9f0955eac0fb5f2213e0fbf59dd6e496",
    "all_pick.yaml":
        "67e171461b259d5ec75c5f71c49678022c9250cfc674390fb615d6f16773083f",
    "all_pick_dag.yaml":
        "3b2304cf471274bf1e81997efc344626cbba7b611e3169d7aee43b8326753b5f",
    "all_pick_dag_v2.yaml":
        "ca2871e96c2888f89b82a5610750ea684903f259056fe998d770de16dcdd18d7",
    "all_pick_v2.yaml":
        "481ffa2ef0a9da471adc487779bcbe5d32e06a064ac279a67dbe236d94771a63",
}


class _CannedContext(ResolutionContext):
    """Two candidates with uneven weights, so every prompt shape is exercised."""

    def __init__(self, stream: list, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._stream = stream

    def call_json(
        self,
        prompt: str,
        *,
        expected_key: str | None = None,
        response_schema: dict | None = None,
        category: str = "",
        method: str = "",
        step: str = "",
    ) -> Any:
        self._stream.append([category, method, step, prompt])
        if expected_key == "value":
            return f"{category}{_MARKER}"
        if expected_key == "candidates":
            return [f"{category}{_MARKER}_a", f"{category}{_MARKER}_b"]
        if expected_key == "weights":
            return [0.7, 0.3]
        return {"distribution": "uniform"}


class _CannedGenerator(IdentityGeneratorConfigurable):
    def __init__(self) -> None:
        super().__init__(client=object())
        self.stream: list[list[str]] = []

    def _build_resolution_context(self, system_instruction: str) -> ResolutionContext:
        return _CannedContext(self.stream, client=self.client, system_instruction=system_instruction)


def _strategy_files() -> list[Path]:
    return [p for p in sorted(_STRATEGY_DIR.glob("*.yaml")) if p.name not in _NON_STRATEGY_FILES]


def _prompt_stream(strategy_path: Path, tmp_path: Path) -> list[list[str]]:
    declared = yaml.safe_load(strategy_path.read_text(encoding="utf-8"))["categories"]
    schema_path = tmp_path / "flat_schema.json"
    schema_path.write_text(
        json.dumps({
            "instruction": ["You are generating a persona."],
            "categories": {name: {"description": f"desc for {name}"} for name in declared},
        }),
        encoding="utf-8",
    )
    # ``generate_evaluate_random_pick`` samples its answer, and that answer feeds the
    # next category's context block. Seeding makes the stream reproducible without
    # making *generation* reproducible -- nothing in src/ is seeded.
    random.seed(0)
    generator = _CannedGenerator()
    generator.generate_identity(str(schema_path), strategy_file=str(strategy_path))
    return generator.stream


def test_every_strategy_yaml_has_an_expected_digest():
    """A new strategy must be pinned too, rather than silently going unguarded."""
    assert {path.name for path in _strategy_files()} == set(EXPECTED_DIGESTS)


@pytest.mark.parametrize("strategy_path", _strategy_files(), ids=lambda p: p.name)
def test_rendered_prompts_match_the_pre_refactor_bytes(strategy_path, tmp_path):
    stream = _prompt_stream(strategy_path, tmp_path)
    assert stream, f"{strategy_path.name} rendered no prompt at all"

    blob = json.dumps(stream, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    assert digest == EXPECTED_DIGESTS[strategy_path.name], (
        f"{strategy_path.name}: the rendered prompt stream changed. See this module's "
        f"docstring before touching the expected digest."
    )
