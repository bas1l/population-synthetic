# Research Report: Claude Code CLI Tool Context Injection

**Date:** 2026-05-19
**Author:** Basil + Claude
**Status:** Complete -- findings documented
**Related:** `docs/development/debug/claude-code-client-persistent-stream-performance-analysis-2026-05-19.md`

---

## Problem Statement

The Claude Code CLI injects ~59,000 tokens of tool definitions (70+ tools, MCP schemas, anti-distillation decoys) into the system prompt of **every** API call, regardless of whether the tools are needed. For programmatic batch workloads (identity generation via `ClaudeCodeClient`), this means 98% of all tokens processed are tool context the model never uses. No CLI flag or configuration tested suppresses this injection.

This report documents an exhaustive investigation into the mechanism, available flags, community workarounds, and alternative paths.

---

## 1. What Was Tested Locally (and Failed)

| Flag / Setting | Behaviour | Token Impact |
|----------------|-----------|-------------|
| `--allowedTools ""` | Process starts, tools still injected | None -- controls permissions, not injection |
| `--max-turns 1` | Prevents multi-turn tool *use* | None -- tools still in context |
| `--no-session-persistence` | Prevents session file contention | None -- unrelated to tools |
| No flag combination tested | -- | All produce ~59K `cache_creation_input_tokens` on cold start |

Documented in plan Task 0.6: `docs/development/plans/active/claude-code-client-persistent-stream-retry.md`

---

## 2. Flags and Settings That Do NOT Suppress Injection

### `--allowedTools` / `--disallowedTools`

These are **permission filters**, not context reducers. They control which tools Claude is allowed to *execute* without a user prompt, but the tool schemas are still sent to the API.

> "The --allowedTools flag is a security/permission filter, not a token optimization mechanism"

**Source:** [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference)

### `disabledTools` in `.claude/settings.json`

Prevents tool invocation but **does not remove tool schemas from context**.

> GitHub Issue [#30480](https://github.com/anthropics/claude-code/issues/30480): "Disabled system tools still consume context" -- Closed as wontfix, but the behaviour is acknowledged.

**Source:** [GitHub Issue #30480](https://github.com/anthropics/claude-code/issues/30480)

### `--bare` flag

Skips auto-discovery of hooks, skills, plugins, MCP servers, and CLAUDE.md files. However:

- Built-in tools (~40 definitions, ~41K tokens) are **still injected**
- **Breaks subscription/OAuth auth** -- requires `ANTHROPIC_API_KEY` environment variable
- Reduces from ~59K to ~41K tokens (by dropping MCP/skills), but the built-in tool overhead remains

**Source:** [Claude Code Headless/Programmatic Docs](https://code.claude.com/docs/en/headless)

---

## 3. Open GitHub Issues (Community Confirmation)

### [#54716](https://github.com/anthropics/claude-code/issues/54716) -- "Allow opt-out of built-in deferred tools via settings"

- **Status:** Open (as of 2026-05-19)
- Proposes a `disabledBuiltinTools` setting that would actually remove tool schemas from context
- Would save ~10-20K tokens by removing unused built-in tools
- Not yet implemented

### [#30480](https://github.com/anthropics/claude-code/issues/30480) -- "Disabled system tools still consume context"

- **Status:** Closed (acknowledged but not fixed)
- Confirms that `disabledTools` in settings only prevents execution, not injection
- The tool schemas remain in the system prompt regardless

### [#11364](https://github.com/anthropics/claude-code/issues/11364) -- "Lazy-load MCP tool definitions"

- **Status:** Closed (marked as duplicate)
- Led to the Tool Search feature, but this only applies to MCP tools, not built-in tools
- Built-in tools remain always-loaded

### [#44536](https://github.com/anthropics/claude-code/issues/44536) -- "Lazy context loading: extend ToolSearch pattern to all context components"

- **Status:** Open
- Proposes extending deferred loading to all context (not just MCP tools)
- Would address the built-in tool overhead if implemented

### [#20873](https://github.com/anthropics/claude-code/issues/20873) -- "Feature request: `--no-tools` or `--minimal` flag"

- **Status:** Open
- Community request for a flag to run Claude CLI as a pure LLM interface with no tools
- Not yet implemented

### [#52979](https://github.com/anthropics/claude-code/issues/52979) -- Excessive token usage in Claude Code CLI

- **Status:** Open
- Bug report documenting the broader token usage problem

---

## 4. Anti-Distillation System (Server-Side Injection)

The Claude Code source (leaked March 2026) revealed an anti-distillation mechanism:

- **Flag:** `ANTI_DISTILLATION_CC` in `claude.ts`
- **Behaviour:** Sends `anti_distillation: ['fake_tools']` in API requests
- **Server action:** Silently adds decoy tool definitions to the system prompt
- **Purpose:** Corrupts training data for anyone recording API traffic to train competing models
- **Gate:** Only activates for first-party CLI sessions (controlled by `tengu_anti_distill_fake_tool_injection` GrowthBook feature flag)

This means the 59K token count includes both real tools AND fake anti-distillation tools injected server-side. There is no client-side way to suppress the server-side injection.

**Sources:**
- [alex000kim.com -- "The Claude Code Source Leak"](https://alex000kim.com/posts/2026-03-31-claude-code-source-leak/)
- [winbuzzer.com -- "Claude Code Source Leak Exposes Anti-Distillation Traps"](https://winbuzzer.com/2026/04/01/claude-code-source-leak-anti-distillation-traps-undercover-mode-xcxwbn/)

---

## 5. `ENABLE_TOOL_SEARCH` Environment Variable

Documented values: `true | false | auto | auto:N`

- Controls on-demand tool loading for MCP tools
- **Not tested locally** -- listed as Experiment 1.1 in the remediation plan
- Likely only affects MCP/deferred tools, not built-in tools
- When set to `auto:5`, activates at 5% context threshold

**Source:** [Claude Code Environment Variables](https://code.claude.com/docs/en/env-vars)

---

## 6. Alternative Paths That Bypass the Problem

### Direct Anthropic Python SDK

The `anthropic` Python package's `messages.create()` call accepts an optional `tools` parameter. Omitting it entirely results in **zero tool overhead**.

```python
from anthropic import Anthropic
client = Anthropic()
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    messages=[{"role": "user", "content": "..."}],
    # No tools parameter = zero tool context
)
```

**Token reduction:** 59K -> 0 per call (100% elimination)
**Constraint:** Requires `ANTHROPIC_API_KEY`. Billed per-token (separate from Claude subscription).

**Cost estimate for 10-identity batch (Haiku):**
- Input: ~150K tokens x $1/M = $0.15
- Output: ~60K tokens x $5/M = $0.30
- **Total: ~$0.45 per batch**

New Anthropic accounts receive $5 in free trial credits (no credit card required, SMS verification only, 14-day expiry). This covers ~110 identities before requiring payment.

**Source:** [Anthropic API Messages Documentation](https://platform.claude.com/docs/en/api/messages)

### Agent SDK Python (`claude-agent-sdk`)

Offers `allowed_tools` parameter claiming to limit which tools are loaded:

```python
from claude_agent_sdk import query, ClaudeAgentOptions
async for message in query(
    prompt="...",
    options=ClaudeAgentOptions(allowed_tools=["Read", "Edit"])
):
    print(message)
```

**Uncertainty:** Still a subprocess wrapper underneath. Unclear whether `allowed_tools` reduces API-level token injection or just SDK-level execution permissions.

**Source:** [Agent SDK Overview](https://code.claude.com/docs/en/agent-sdk/overview)

### Tool Search Tool (API-Level Beta)

Available through the Anthropic API (not CLI). Tools marked `defer_loading: true` are not sent upfront -- the model uses a Tool Search tool to discover and load them on demand.

**Token reduction:** ~85% (191K tokens preserved vs 122K baseline in Anthropic's benchmark)
**Constraint:** API-only; requires beta header `advanced-tool-use-2025-11-20`

**Source:**
- [Tool Search Tool Documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [Anthropic Engineering -- Advanced Tool Use](https://www.anthropic.com/engineering/advanced-tool-use)

---

## 7. Additional References

### Official Documentation

- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference)
- [Run Claude Code Programmatically](https://code.claude.com/docs/en/headless)
- [Manage Tool Context (API Best Practices)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/manage-tool-context)
- [Claude Code Environment Variables](https://code.claude.com/docs/en/env-vars)
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)

### Community Analysis

- [paddo.dev -- "Claude Code's Hidden MCP Flag: 32k Tokens Back"](https://paddo.dev/blog/claude-code-hidden-mcp-flag/)
- [madewithlove.com -- "Your Claude Code is burning through tokens"](https://madewithlove.com/blog/your-claude-code-is-burning-through-tokens-heres-how-to-fix-it/)
- [productcompass.pm -- "Claude Code Pricing: Subscriptions vs API"](https://www.productcompass.pm/p/claude-code-pricing)

---

## 8. Conclusion

**There is no CLI-level solution to suppress tool context injection below ~41K tokens.** The `--allowedTools`, `disabledTools`, and `--max-turns` mechanisms all control tool *execution permissions*, not *context injection*. The `--bare` flag reduces MCP/skill overhead (~18K savings) but still injects ~41K of built-in tools and breaks subscription auth.

The only confirmed path to zero tool overhead is the **direct Anthropic Python SDK** with no `tools` parameter. This eliminates the 59K-token injection entirely, reducing per-call context from ~60K to ~500 tokens and projected per-call latency from 8-16s to 1-3s.

Anthropic has open issues ([#54716](https://github.com/anthropics/claude-code/issues/54716), [#20873](https://github.com/anthropics/claude-code/issues/20873)) requesting a `--no-tools` flag or `disabledBuiltinTools` setting. If implemented, these would resolve the problem at the CLI level. Until then, the SDK path is the only way forward for token-sensitive batch workloads.
