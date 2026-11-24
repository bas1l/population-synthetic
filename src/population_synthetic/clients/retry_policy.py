"""Shared retry-attempt policy for the LLM call stack.

A single persona generation retries at four independent layers:

1. **Transport** -- the client's own backoff loop around one HTTP/CLI call
   (``OllamaClient``, ``OpenAICompatClient``, ``ClaudeCodeClient``).
2. **Call** -- ``IdentityGeneratorConfigurable._call_llm_json`` re-issues the
   whole call when the response is unparseable or misses the expected key.
3. **Reconcile** -- the weight/candidate count loop inside the
   ``generate_evaluate_*`` methods.
4. **Slot** -- the parallel runner's round loop, which re-runs every persona
   that failed.

All four share this policy: without ``retry_until_success`` each layer keeps
its own small default; with it, each layer retries up to
:data:`MAX_RETRY_ATTEMPTS`. The ceiling is deliberate -- "until success" means
"do not give up on a flaky model", not "hang forever on a broken one". A layer
that reaches the ceiling fails loudly.

:data:`FATAL_ERROR_CATEGORIES` are the ``error_category`` values that no amount
of retrying can fix (a missing model, a rejected key). Layers above the
transport must re-raise those immediately instead of consuming the budget.
"""

MAX_RETRY_ATTEMPTS = 100

FATAL_ERROR_CATEGORIES = frozenset({"auth", "model_limitation"})


def max_attempts(retry_until_success: bool, default: int) -> int:
    """Attempt budget for one retry layer.

    Returns :data:`MAX_RETRY_ATTEMPTS` when *retry_until_success* is set,
    otherwise *default* (the layer's own small cap).
    """
    return MAX_RETRY_ATTEMPTS if retry_until_success else default
