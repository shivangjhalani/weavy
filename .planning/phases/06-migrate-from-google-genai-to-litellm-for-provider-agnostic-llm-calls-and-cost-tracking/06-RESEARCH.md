# Phase 6: Migrate from google-genai to litellm - Research

**Researched:** 2026-03-27
**Domain:** LLM provider abstraction — replacing google-genai SDK with litellm for completions, embeddings, and function calling
**Confidence:** HIGH (verified against installed litellm 1.82.4 source + official litellm docs)

---

## Summary

Phase 6 replaces `google-genai` SDK calls with `litellm` calls across three usage sites: `AgentHarness` (completion + function calling loop), `compress.py` (standalone Gemini completion for log compression), and `embeddings.py` (embedding generation). Transcription in `transcribe.py` already uses litellm and stays unchanged.

The core architectural shift is from google-genai's stateful `client.models.generate_content()` pattern with SDK-typed objects (`types.Content`, `types.Part`, `types.FunctionDeclaration`) to litellm's stateless `litellm.completion()` pattern with OpenAI-compatible message dicts and JSON-parsed tool call arguments. The agent loop conversation history representation changes from a list of `types.Content` objects to a list of plain Python dicts.

The `tools.py` module has the largest surface area change: 9 `types.FunctionDeclaration` objects built from `types.Schema` must be replaced with OpenAI-format tool dicts. The `AgentHarness` class type annotations and internal dispatch logic must be rewritten to match litellm's response shape. Cost tracking — the new capability this phase adds — is a single `litellm.completion_cost(response)` call after each completion.

**Primary recommendation:** Migrate module by module bottom-up (embeddings → compress → tools declarations → harness → scripts), update tests to match the new call shapes, and add cost accumulation to the harness `run()` return.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| litellm | 1.82.4 (installed) | Unified completion + embedding + transcription | Already in project, already used for transcription; adds OpenAI-compat layer over every provider |
| google-genai | 1.68.0 (installed) | Currently primary SDK — to be removed from completion/embedding call sites | Stays in pyproject.toml until all call sites are migrated; can be removed after phase completes |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tiktoken | 0.12.0 (installed) | Token counting for compression threshold | Unchanged — not litellm-coupled |
| python-dotenv | installed | .env loading | Unchanged — GEMINI_API_KEY stays, litellm reads it via `os.environ["GEMINI_API_KEY"]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| litellm | openai SDK with gemini compat base_url | More fragile; litellm already in project and tested for Groq transcription |
| litellm | instructor | Adds structured-output dependency; not needed here |

**No new package installs required.** litellm 1.82.4 is already present and supports all required operations.

---

## Architecture Patterns

### Module Migration Map

| Module | Current API | Post-Migration API | Scope |
|--------|------------|-------------------|-------|
| `lifeos/core/embeddings.py` | `genai.Client().models.embed_content()` | `litellm.embedding()` | ~15 lines |
| `lifeos/agent/compress.py` | `client.models.generate_content()` with `genai.Client` type annotation | `litellm.completion()` — no client object | ~25 lines |
| `lifeos/agent/tools.py` | `types.FunctionDeclaration` + `types.Schema` | OpenAI-format tool dicts (plain Python) | ~120 lines of declarations |
| `lifeos/agent/harness.py` | `genai.Client`, `types.Content`, `types.Part`, `types.FunctionResponse` | stateless `litellm.completion()` with dict messages | ~80 lines |
| `scripts/ingest.py` | `genai.Client()` construction, `types.ThinkingConfig` | litellm kwargs for reasoning | ~20 lines |
| `tests/test_harness.py` | Mock objects mimicking google-genai shapes | Mocks for litellm response shapes | full rewrite of mock helpers |
| `tests/test_compression.py` | `mock_client.models.generate_content` | patch `litellm.completion` | ~40 lines |

### Pattern 1: litellm Completion (Stateless)

**What:** No client object. Call `litellm.completion()` directly. Messages are plain dicts.
**When to use:** Every LLM call — harness loop, compress_log, future query agent.

```python
# Source: https://docs.litellm.ai/docs/providers/gemini
import litellm
import os

os.environ["GEMINI_API_KEY"] = "..."  # already in .env

response = litellm.completion(
    model="gemini/gemini-2.5-flash",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
    ],
    tools=tools,          # list of OpenAI-format tool dicts
    tool_choice="auto",
)
```

**Model name format for Gemini via Google AI Studio:** `"gemini/gemini-2.5-flash"` (prefix required).

### Pattern 2: OpenAI-Format Tool Definitions

**What:** Tool declarations as plain Python dicts, not `types.FunctionDeclaration` objects.
**When to use:** `tools.py` — replace all 9 `types.FunctionDeclaration` blocks.

```python
# Source: https://docs.litellm.ai/docs/completion/function_call
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_nodes_by_alias",
            "description": "Find graph nodes whose alias set contains the given alias.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {"type": "string"},
                },
                "required": ["alias"],
            },
        },
    },
    # ... 8 more
]
```

**Nested object parameters** (used in `create_episode_spans` spans array):

```python
{
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "start_offset": {"type": "integer"},
            "end_offset": {"type": "integer"},
            "summary": {"type": "string"},
        },
        "required": ["start_offset", "end_offset", "summary"],
    },
}
```

### Pattern 3: litellm Response Shape for Tool Calls

**What:** `response.choices[0].message.tool_calls` is a list of `ChatCompletionMessageToolCall` objects. Arguments are a **JSON string**, not a dict.
**When to use:** `harness.py` dispatch loop — replaces `fc_parts` extraction logic.

```python
# Source: litellm installed types at .devenv/state/venv/lib/python3.12/site-packages/litellm/types/utils.py
message = response.choices[0].message
finish_reason = response.choices[0].finish_reason  # "stop", "tool_calls", "length"

tool_calls = message.tool_calls  # None or list[ChatCompletionMessageToolCall]
if tool_calls:
    for tc in tool_calls:
        name = tc.function.name          # str
        args = json.loads(tc.function.arguments)  # dict — arguments IS a JSON string
        call_id = tc.id                  # str — echo back in tool result
```

**CRITICAL:** `tc.function.arguments` is always a JSON string. Use `json.loads()` before passing to tool callables.

### Pattern 4: Agentic Loop Conversation History

**What:** Messages are dicts appended to a running list. Tool results use `role: "tool"`.
**When to use:** `harness.py` — replaces `types.Content`/`types.Part` construction.

```python
# Source: https://docs.litellm.ai/docs/completion/function_call
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_message},
]

while True:
    response = litellm.completion(model=model, messages=messages, tools=tools)
    msg = response.choices[0].message

    # Append assistant turn (as dict)
    messages.append(msg.to_dict() if hasattr(msg, "to_dict") else dict(msg))

    tool_calls = msg.tool_calls
    if not tool_calls:
        return msg.content  # done

    # Dispatch and append tool results
    for tc in tool_calls:
        args = json.loads(tc.function.arguments)
        result = tools_dict[tc.function.name](**args)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": tc.function.name,
            "content": json.dumps({"result": result}),
        })
```

**Appending assistant message:** Use `response.choices[0].message` object directly or convert to dict. litellm message objects support dict conversion.

### Pattern 5: litellm Embedding

**What:** `litellm.embedding()` with `model="gemini/gemini-embedding-001"`. `task_type` parameter is supported.
**When to use:** `embeddings.py` — replaces `client.models.embed_content()`.

```python
# Source: https://docs.litellm.ai/docs/embedding/supported_embedding
import litellm

response = litellm.embedding(
    model="gemini/gemini-embedding-001",
    input=[text],
    task_type="RETRIEVAL_DOCUMENT",  # or "RETRIEVAL_QUERY"
)
values = response["data"][0]["embedding"]  # list[float]
```

**Confidence note:** The litellm docs page for supported embeddings lists `text-embedding-004` as the example model, not `gemini-embedding-001`. However, the search found explicit usage examples of `model="gemini/gemini-embedding-001"` with `task_type` in litellm issue threads. This should be verified with a quick smoke test at the start of Phase 6 execution. Fallback: use `"gemini/text-embedding-004"` if `gemini-embedding-001` fails.

### Pattern 6: Standalone Completion (compress.py)

**What:** Single `litellm.completion()` call, no client object passed around.
**When to use:** `compress_log()` — replaces `client.models.generate_content()`.

```python
# Source: https://docs.litellm.ai/docs/completion/function_call
import litellm

response = litellm.completion(
    model=model,  # "gemini/gemini-2.5-flash"
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Compress these log entries:\n\n{older_json}"},
    ],
    response_format={"type": "json_object"},  # replaces response_mime_type="application/json"
)
compressed_entry = json.loads(response.choices[0].message.content)
```

**Signature change:** `compress_log(log_entries, client, model)` becomes `compress_log(log_entries, model)` — drop the `client` parameter entirely.

### Pattern 7: Cost Tracking

**What:** `litellm.completion_cost(response)` returns USD float. Also available from `response._hidden_params["response_cost"]`.
**When to use:** After each `litellm.completion()` call in the harness loop.

```python
# Source: https://docs.litellm.ai/docs/completion/token_usage
from litellm import completion_cost

response = litellm.completion(...)
cost = completion_cost(completion_response=response)  # float, USD

# Accumulate across all turns in the agent loop
total_cost += cost
```

**Token usage:**
```python
usage = response.usage
usage.prompt_tokens      # int
usage.completion_tokens  # int
usage.total_tokens       # int
```

### Pattern 8: Thinking / Reasoning

**What:** Use `reasoning_effort` parameter instead of `types.ThinkingConfig`. Maps to Gemini's `thinking_budget`.
**When to use:** Replace `thinking_config=types.ThinkingConfig(thinking_budget=N)` in harness and ingest.py.

```python
# Source: https://docs.litellm.ai/docs/providers/gemini
response = litellm.completion(
    model="gemini/gemini-2.5-flash",
    messages=messages,
    reasoning_effort="high",   # "none" | "low" | "medium" | "high"
    # OR pass budget_tokens directly via extra_body:
    # extra_body={"thinking": {"type": "enabled", "budget_tokens": 8000}}
)
```

**Mapping (litellm 1.82.x):**
| `reasoning_effort` | `budget_tokens` |
|-------------------|----------------|
| `"none"` | 0 (off) |
| `"low"` | 1024 |
| `"medium"` | 2048 |
| `"high"` | 4096 |

**Thinking content in response:** When thinking is active, `response.choices[0].message.content` may contain reasoning. The response does NOT expose a separate `thinking_text` field at the top level — the harness's current logic extracting `p.thought` parts needs to be dropped. Cost tracking of reasoning tokens uses `response.usage` which includes `reasoning_tokens` when present.

### Anti-Patterns to Avoid

- **Keep `genai.Client` instance in signatures:** After migration, no google-genai objects should be passed between modules. `compress_log` and `run_compression_pass` signatures must drop `client: genai.Client`.
- **Access tool call args as dict directly:** `tc.function.arguments` is a JSON string — always `json.loads()` it.
- **Use `types.Part.from_function_response()`:** This was a known bug in google-genai. Irrelevant after migration.
- **Call `response.text` on litellm response:** litellm responses do not have a `.text` attribute. Use `response.choices[0].message.content`.
- **Build `types.Content` or `types.Part` objects:** All message history is plain Python dicts.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Provider-specific tool format translation | Custom adapter per provider | `litellm.completion(tools=[...])` | litellm translates OpenAI format to Gemini format automatically |
| Cost calculation | Manual token * price arithmetic | `litellm.completion_cost(response)` | Uses live pricing from api.litellm.ai; handles thinking token pricing |
| Retry / backoff | Custom retry loop | `litellm.completion()` built-in retry params | `num_retries`, `timeout` params available |
| JSON response parsing | Custom mime type handling | `response_format={"type": "json_object"}` | Standard OpenAI param, litellm maps to `response_mime_type` per provider |

---

## Common Pitfalls

### Pitfall 1: `response.text` Does Not Exist on litellm Response

**What goes wrong:** Current `harness.py` calls `response.text` on the final response. litellm `ModelResponse` has no `.text` attribute.
**Why it happens:** google-genai SDK has `.text` as a convenience property; litellm follows the OpenAI spec.
**How to avoid:** Use `response.choices[0].message.content` everywhere. In the harness `run()` return: `return response.choices[0].message.content`.
**Warning signs:** `AttributeError: 'ModelResponse' object has no attribute 'text'` at runtime.

### Pitfall 2: Tool Call Arguments Are a JSON String

**What goes wrong:** Passing `tc.function.arguments` directly as kwargs to the tool callable will fail — it's a string like `'{"alias": "foo"}'`, not a dict.
**Why it happens:** OpenAI API spec encodes arguments as a JSON-serialized string.
**How to avoid:** Always `args = json.loads(tc.function.arguments)` before `tools_dict[name](**args)`.
**Warning signs:** `TypeError: tool_callable() argument after ** must be a mapping, not str`.

### Pitfall 3: System Prompt Issues with Gemini on litellm (MEDIUM confidence)

**What goes wrong:** Issue #14947 on litellm GitHub reported `"Unknown name 'system_instruction'"` errors with system messages on Google AI Studio via litellm in some versions.
**Why it happens:** litellm translates `role: "system"` messages to Gemini's `system_instruction` field; in some versions the serialization was broken.
**How to avoid:** Test system prompt handling in a smoke test before implementing full harness. Verified in litellm docs as officially supported with standard `{"role": "system", "content": "..."}` format. The closed issue was marked "not planned" after no reproduction details were given — may have been a misconfiguration.
**Warning signs:** `400 Bad Request` or `Unknown name 'system_instruction'` errors on the first completion call.
**Confidence:** MEDIUM — issue exists in tracker but may not affect v1.82.4.

### Pitfall 4: finish_reason Values Differ

**What goes wrong:** Current harness checks for absence of `fc_parts` to detect "done". litellm sets `finish_reason="tool_calls"` when tools are present. The absence of `tool_calls` in the message is the reliable signal.
**Why it happens:** Different APIs signal tool use differently; litellm normalizes to OpenAI values.
**How to avoid:** Check `message.tool_calls is None or len(message.tool_calls) == 0` to detect the terminal state, not `finish_reason`.

### Pitfall 5: Harness Tests Are Coupled to google-genai Mock Shapes

**What goes wrong:** All 9 tests in `test_harness.py` use mock objects that mimic `google.genai` response shapes (`MockFunctionCall`, `MockPart`, `MockContent`, etc.) and import `from google.genai import types` to verify `types.Part(function_response=...)` construction.
**Why it happens:** Tests were written against the google-genai API.
**How to avoid:** Rewrite mock helpers to mimic litellm `ModelResponse` shapes. The `test_function_response_includes_fc_id` test logic no longer applies (litellm doesn't echo IDs in the same way). Focus new tests on: correct JSON parsing of arguments, correct `role: "tool"` message construction, and correct `message.content` return.

### Pitfall 6: compress.py Client + Model Parameter Signature

**What goes wrong:** Current `compress_log(log_entries, client, model)` and `run_compression_pass(..., client, model)` take a `genai.Client`. After migration, there is no client — litellm is stateless. Callers in `ingest.py` and `test_compression.py` pass `client=client`.
**Why it happens:** google-genai required a client instance.
**How to avoid:** Drop `client` parameter from both functions. Keep `model` parameter so the caller can still specify the model. Update `test_compression.py` mock to patch `litellm.completion` instead of `mock_client.models.generate_content`.

### Pitfall 7: gemini-embedding-001 Model Name Needs Verification

**What goes wrong:** The litellm supported embeddings docs list `text-embedding-004` as the primary Gemini example. `gemini-embedding-001` support exists but is not prominently documented.
**Why it happens:** litellm docs lag behind available models.
**How to avoid:** Add a Wave 0 smoke test that calls `litellm.embedding(model="gemini/gemini-embedding-001", input=["test"])` before writing any implementation. If it errors, fall back to the config default and document the finding.

### Pitfall 8: Thinking Content Extraction Logic Breaks

**What goes wrong:** Current `harness.py` has logic to extract `thinking_text` by checking `p.thought` on google-genai `Part` objects. litellm does not expose thinking content in the same way — it may appear prepended in `message.content` or in `message.provider_specific_fields`.
**Why it happens:** google-genai exposes `Part.thought=True` for thinking parts; litellm uses a different structure.
**How to avoid:** Drop the thinking text extraction from the harness (the tracer `on_llm_response` currently captures it). If thinking content is needed in traces, investigate `response.choices[0].message` fields after a live call. The primary goal is correct function calling behavior, not thinking content extraction.

---

## Code Examples

### Full litellm Agentic Loop (Reference Pattern)

```python
# Source: https://docs.litellm.ai/docs/completion/function_call
import json
import litellm
from lifeos.core.config import get_config

def run(system_prompt: str, user_message: str, model: str, tools_dict: dict, tools: list) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    total_cost = 0.0

    while True:
        response = litellm.completion(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        total_cost += litellm.completion_cost(completion_response=response)

        msg = response.choices[0].message
        # Append assistant turn to history
        messages.append(msg.to_dict() if hasattr(msg, "to_dict") else {"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})

        if not msg.tool_calls:
            return msg.content  # no tool calls = done

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = tools_dict[tc.function.name](**args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps({"result": result}),
            })
```

### litellm Embedding (Reference Pattern)

```python
# Source: https://docs.litellm.ai/docs/embedding/supported_embedding
import litellm

def embed_text(text: str) -> list[float]:
    response = litellm.embedding(
        model="gemini/gemini-embedding-001",
        input=[text],
        task_type="RETRIEVAL_DOCUMENT",
    )
    return response["data"][0]["embedding"]
```

### OpenAI-Format Tool Declaration (Reference Pattern)

```python
# Source: https://docs.litellm.ai/docs/completion/function_call
# Replaces types.FunctionDeclaration(name=..., parameters=types.Schema(...))
search_nodes_by_alias_tool = {
    "type": "function",
    "function": {
        "name": "search_nodes_by_alias",
        "description": "Find graph nodes whose alias set contains the given alias (exact match). Use as the first disambiguation step before creating a new node.",
        "parameters": {
            "type": "object",
            "properties": {
                "alias": {"type": "string"},
            },
            "required": ["alias"],
        },
    },
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `genai.Client` stateful object | `litellm.completion()` stateless calls | This phase | Simpler module boundaries; no client to thread through |
| `types.Content` + `types.Part` for history | Plain dict message list | This phase | Standard format; any provider can consume |
| `types.FunctionDeclaration` + `types.Schema` | OpenAI-format tool dicts | This phase | JSON schema; no SDK imports in tools.py |
| `response.text` (google-genai shortcut) | `response.choices[0].message.content` | This phase | OpenAI spec compliance |
| `types.ThinkingConfig(thinking_budget=N)` | `reasoning_effort="low"/"medium"/"high"/"none"` | This phase | Provider-agnostic reasoning control |

**Removed after phase:**
- `from google import genai` — zero remaining imports
- `from google.genai import types` — zero remaining imports
- `google-genai` package can be removed from `pyproject.toml` after all call sites verified

---

## Open Questions

1. **gemini-embedding-001 exact model name via litellm**
   - What we know: `litellm.embedding(model="gemini/gemini-embedding-001", ...)` is used in community examples with `task_type`
   - What's unclear: Whether `task_type` is passed through correctly in litellm 1.82.4 for the `gemini/` prefix (vs. vertex prefix)
   - Recommendation: Wave 0 smoke test in Wave 0 plan. If `gemini-embedding-001` fails, check if `gemini/text-embedding-004` is the correct name and update config default accordingly.

2. **Thinking content in tracer**
   - What we know: Current harness extracts `thinking_text` from `p.thought`-flagged parts and passes it to `tracer.on_llm_response()`. litellm does not expose this the same way.
   - What's unclear: Whether litellm 1.82.4 exposes thinking content in the response for `gemini/gemini-2.5-flash` at all, and in what field.
   - Recommendation: Drop `thinking_text` from `tracer.on_llm_response()` call in the migrated harness, or pass `None` always. Thinking tracing is a nice-to-have, not load-bearing.

3. **`message.to_dict()` availability**
   - What we know: litellm `Message` inherits from `OpenAIObject` which has dict-like access
   - What's unclear: Whether `to_dict()` or `model_dump()` is the correct method to serialize for appending to messages list
   - Recommendation: Test both. Safest fallback: `{"role": msg.role, "content": msg.content, "tool_calls": [tc.__dict__ for tc in (msg.tool_calls or [])]}`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|---------|
| litellm | All LLM calls | Yes | 1.82.4 | — |
| google-genai | Being removed | Yes | 1.68.0 | — (removing it) |
| GEMINI_API_KEY | litellm gemini/ calls | Yes (in .env) | — | — |
| GROQ_API_KEY | Transcription (unchanged) | Yes (in .env) | — | — |
| FalkorDB | Agent tools | Yes (devenv docker) | latest | — |

No missing dependencies. This is a pure code migration within existing installed packages.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `devenv shell -- uv run pytest tests/ -x -q` |
| Full suite command | `devenv shell -- uv run pytest tests/ -v` |

### Phase Requirements → Test Map

This phase has no formal requirement IDs but has implicit behavioral requirements:

| Behavior | Test Type | Automated Command | File Exists? |
|----------|-----------|-------------------|-------------|
| Harness runs agentic loop via litellm | unit | `pytest tests/test_harness.py -x` | Yes — needs full rewrite |
| Tool call args correctly JSON-parsed | unit | `pytest tests/test_harness.py::test_harness_dispatches_tool_call -x` | Yes — new mock shape |
| Tool result message uses `role: "tool"` | unit | `pytest tests/test_harness.py::test_harness_function_response_format -x` | Needs new test |
| compress_log calls litellm not genai client | unit | `pytest tests/test_compression.py -x` | Yes — needs mock patch update |
| embed_text returns list[float] via litellm | unit | `pytest tests/test_tools.py -x` | Needs verify |
| GEMINI_API_KEY propagates to litellm | unit | `pytest tests/test_config.py -x` | Existing |
| Full ingest.py smoke test (live API) | integration | `pytest -m integration` | Not present |

### Sampling Rate
- **Per task commit:** `devenv shell -- uv run pytest tests/ -x -q`
- **Per wave merge:** `devenv shell -- uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_harness.py` — Mock helper classes need full rewrite to mimic litellm `ModelResponse` shape (no google-genai types)
- [ ] `tests/test_compression.py` — `compress_log` test calls must patch `litellm.completion`, not `mock_client.models.generate_content`; signature changes from `(entries, client)` to `(entries, model)`
- [ ] New test: `test_harness_tool_role_message_format` — verify `role: "tool"` with `tool_call_id` in messages
- [ ] New test: `test_embed_text_returns_list_float` — verify `embed_text()` returns `list[float]` via litellm

---

## Sources

### Primary (HIGH confidence)
- litellm installed source `/home/shivang/shivang/projs/LifeOS/.devenv/state/venv/lib/python3.12/site-packages/litellm/types/utils.py` — `ChatCompletionMessageToolCall`, `Function`, `Message` type definitions
- https://docs.litellm.ai/docs/completion/function_call — tool definition format, response shape, agentic loop pattern
- https://docs.litellm.ai/docs/providers/gemini — `gemini/` model prefix, system message format, reasoning_effort parameter
- https://docs.litellm.ai/docs/completion/token_usage — `completion_cost()` usage
- https://docs.litellm.ai/docs/embedding/supported_embedding — embedding call format and response shape

### Secondary (MEDIUM confidence)
- https://github.com/BerriAI/litellm/pull/10141 — Gemini 2.5 Flash thinking/reasoning support implementation details
- Community examples showing `litellm.embedding(model="gemini/gemini-embedding-001", task_type=...)` — gemini-embedding-001 naming
- https://github.com/BerriAI/litellm/issues/14947 — system_instruction issue (closed without fix, v1.77.4 specific, may not affect 1.82.4)

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — litellm 1.82.4 installed, versions verified from disk
- Architecture: HIGH — patterns verified against installed litellm types and official docs
- Pitfalls: MEDIUM-HIGH — most from code inspection + official docs; system_prompt issue is MEDIUM (single report, possibly resolved)
- Embedding model name: MEDIUM — `gemini-embedding-001` name via litellm confirmed in community but not prominently in official docs

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (litellm releases frequently; verify if major version bump before execution)
