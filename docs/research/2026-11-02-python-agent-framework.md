# Python agent framework for the Empório customer-service agent

Research date: 2026-11-02. Deadline: Wed 2026-11-04 23:59 BRT.
Hard constraints: Python 3.12 (`pyproject.toml` already requires `>=3.12`), OpenRouter is the only LLM provider, model chosen by env var.

Method: every claim links to the source that owns it (official docs, GitHub source/releases, PyPI). Package versions, release dates and declared dependencies come from the PyPI JSON API (`https://pypi.org/pypi/<pkg>/json`) on 2026-11-02. Transitive dependency counts come from `uv pip compile --python-version 3.12` on the same day. Some source-level facts were checked inside the published wheel and are linked to the matching file on GitHub. Anything I could not confirm is marked **UNVERIFIED**.

---

## 1. TL;DR

**Recommendation: PydanticAI, installed as `pydantic-ai-slim[openrouter]==2.64.0` (pin it exactly).**
**Runner-up: the plain `openai` SDK (3.x) with a hand-written tool-calling loop.**

How this maps to what the graders look for:

| Grader criterion | Why PydanticAI fits |
|---|---|
| "Solve it in the simplest way possible" | OpenRouter is a **native** provider: `Agent("openrouter:<slug>")` plus `OPENROUTER_API_KEY`, with no base-URL hacks, no API-mode switch and no tracing to turn off ([docs](https://pydantic.dev/docs/ai/models/openrouter/)). The slim install resolves to **20 packages** and pulls no LiteLLM, MCP or web server. |
| Logic / enforced in code | The verified customer id lives in `deps` and tools read it through `RunContext.deps` ([docs](https://pydantic.dev/docs/ai/core-concepts/dependencies/)). The `ctx` parameter is injected at call time and is not part of the tool's argument schema ([source](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/_function_schema.py)), so the model cannot supply or override the id. |
| Clarity | Typed `deps_type` and typed message parts (`ToolCallPart.tool_name/args/tool_call_id`) make the trajectory assertions short and readable. |
| Stability under a 1–2 day deadline | It is the only candidate that is post-1.0 **and** promises no intentional breaking changes in minor releases ([version policy](https://github.com/pydantic/pydantic-ai/blob/main/docs/version-policy.md)). PyPI classifier: `5 - Production/Stable`. |
| Justified decisions / initiative | The loop guard is a first-class setting (`UsageLimits(request_limit=..., tool_calls_limit=...)`). `TestModel` and `FunctionModel` let the scripted-conversation tests run deterministically without spending OpenRouter credits ([source](https://github.com/pydantic/pydantic-ai/tree/main/pydantic_ai_slim/pydantic_ai/models)). |

**Why the plain `openai` SDK is the runner-up:** it is the smallest dependency set (14 packages), has zero framework risk, and is OpenRouter's own documented Python path ([quickstart](https://openrouter.ai/docs/quickstart)). The cost is roughly 60–80 extra lines for the loop, the call cap, history and trajectory. Choose it if the spike shows any PydanticAI and OpenRouter friction. The README story ("the agent loop is ~60 lines I can explain line by line") is also a strong fit for "simplest way possible".

**Why not the OpenAI Agents SDK** (the obvious third choice), in short:
- It defaults to the Responses API.
- It uploads traces to OpenAI, which returns 401 without an OpenAI key.
- It rejects OpenRouter's `vendor/model` slugs when they are passed as strings.
- It is pre-1.0, and minor versions are allowed to break.

Each of these has a workaround (see §3.1), but together they amount to four pieces of config to explain, and none of them helps the solution.

---

## 2. Ranked comparison

| # | Candidate (version, PyPI date) | OpenRouter path | Local context API | Trajectory capture | Multi-turn memory | Guardrails | Loop guard | Maturity | Deps (resolved, py3.12) | Est. LOC* | Risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **PydanticAI** `pydantic-ai-slim` 2.64.0 (2026-10-31) | **Native** `OpenRouterProvider` / `"openrouter:<slug>"`; Chat Completions via `openai` SDK | `deps_type=` + `RunContext[T].deps`; `ctx` is not in the tool schema | `result.new_messages()` → `ToolCallPart(tool_name, args, tool_call_id)` | `message_history=result.all_messages()` | Separate `pydantic-ai-harness` 0.64 (`InputGuardrail`), or a hand-written pre-check | `UsageLimits(request_limit=50 default, tool_calls_limit)` → `UsageLimitExceeded` | v2 stable since 2026-06-23; no intended breaks in minors; ~every 1–3 days | **20** (`[openrouter]`); full `pydantic-ai` = 95 | ~130–160 | Low. Fast cadence, so pin exactly |
| 2 | **Plain `openai`** 3.42.1 (2026-11-01) | `OpenAI(base_url="https://openrouter.ai/api/v1")`, documented by OpenRouter | Your own Python object, never serialised | You record each `tool_calls` entry yourself | A `messages` list you own | Hand-written | Your own `for` loop counter | Stable SDK; 3.0 (2026-08-12) broke custom httpx clients only | **14** | ~190–230 | Lowest. More code to write and test |
| 3 | **OpenAI Agents SDK** `openai-agents` 0.24.0 (2026-10-15) | OpenAI-compatible client **plus** `set_default_openai_api("chat_completions")` or `OpenAIChatCompletionsModel`; LiteLLM/any-llm optional | `Runner.run(context=obj)` → `RunContextWrapper[T].context`, documented as "not sent to the LLM" | `result.new_items` → `ToolCallItem.tool_name`, `.raw_item.arguments` | `SQLiteSession()` (defaults to `:memory:`) | Built in: `@input_guardrail`, tripwire exception | `max_turns` (default 10) → `MaxTurnsExceeded` | 0.x; minor = breaking; ~2–4 weeks per minor | **38** (64 with `[litellm]`) | ~150–180 | Medium. Responses default, tracing 401s, slug parsing |
| 4 | **LangChain 1.x / LangGraph** `langchain` 1.4.8 (2026-11-02), `langgraph` 1.2.19 | `langchain-openrouter` 0.2.9 (`ChatOpenRouter`, `"openrouter:<slug>"`), Beta classifier | `context_schema=` + `ToolRuntime[Ctx].context` | `result["messages"]` → `AIMessage.tool_calls` | `checkpointer=InMemorySaver()` + `thread_id` | Middleware: `@before_agent(can_jump_to=["end"])`, `PIIMiddleware` | `ModelCallLimitMiddleware(run_limit=...)` | 1.x stable; very fast cadence | **42–44** (incl. `langsmith`) | ~150–180 | Medium. Many concepts for a small agent; OpenRouter package in Beta |
| 5 | **Google ADK** `google-adk` 2.13.0 (2026-10-23) | Python: **only via LiteLLM** (`LiteLlm(model="openrouter/...")`), an optional install; the native OpenAI connector is Go-only and experimental | `ToolContext.state` (`temp:` prefix = per invocation); `{key}` templating can inject state into the prompt | `runner.run_async()` events → `event.get_function_calls()` | `InMemorySessionService` | Callbacks / plugins (`before_tool_callback`, ...) | `RunConfig.max_llm_calls` (default 500) | 2.x; very fast cadence | **48**, **81 with LiteLLM** (boto3, tokenizers, huggingface-hub) | ~200–240 | High. LiteLLM in the path, Gemini-first, async plumbing |
| 6 | **Vercel AI SDK for Python** `ai` 0.8.0 (2026-09-29) | No documented OpenRouter path; `ai.get_provider("openai", base_url=...)` exists in source; unprefixed ids route to Vercel AI Gateway | None: `Context` is "Everything that goes into the LLM"; use closures | Events / messages from your own loop | `context.add(...)` in your own loop | Hooks (human-in-the-loop oriented) | No max-steps parameter found; write it yourself | `4 - Beta`; requires Python ≥3.12 | **13** (16 with `[openai]`) | ~180–230 | High. Beta, few docs, OpenRouter path undocumented |

\* LOC = my estimate for agent + 5 tools + in-memory session + CLI, excluding the scripted-conversation runner and tests. These are not measured.

---

## 3. Per-candidate findings

### 3.1 OpenAI Agents SDK (`openai-agents`)

**a. OpenRouter**
- "The SDK uses the Responses API by default". Many other providers lack it and return 404s. The fix is `OpenAIChatCompletionsModel(model=..., openai_client=AsyncOpenAI(base_url=..., api_key=...))` or `set_default_openai_api("chat_completions")` ([models docs](https://openai.github.io/openai-agents-python/models/)).
- The function is defined as `set_default_openai_api(api: Literal["chat_completions", "responses"])` ([source `__init__.py`](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/__init__.py)).
- OpenRouter's only appearance in these docs is a `MultiProvider(openai_base_url="https://openrouter.ai/api/v1", ..., openai_prefix_mode="model_id", unknown_prefix_mode="model_id")` example ([models docs](https://openai.github.io/openai-agents-python/models/)).
- **Gotcha (verified in source):** `MultiProvider` defaults to `openai_prefix_mode="alias"` and `unknown_prefix_mode="error"`. Raised as `UserError(f"Unknown prefix: {prefix}")`, which means `Agent(model="google/gemini-3.8-flash")` passed as a string fails ([source `multi_provider.py`](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/models/multi_provider.py)). Pass a model object instead.
- OpenRouter now serves a Responses endpoint at `/api/v1/responses`. It is **stateless**: "requests with `store: true` or a non-null `previous_response_id` are rejected with a 400". It supports function calling ([OpenRouter Responses overview](https://openrouter.ai/docs/api_reference/responses/overview)). Its basic-usage page still carries a beta warning ([basic usage](https://openrouter.ai/docs/api_reference/responses/basic-usage)), so Chat Completions remains the safer path.
- Other documented provider caveats ([models docs](https://openai.github.io/openai-agents-python/models/)):
  - Unreliable streamed tool-call deltas: use `buffer_streamed_tool_calls=True`.
  - Unsupported `response_format` returns 400.
  - Responses-only fields are silently dropped on Chat Completions (`strict_feature_validation=True` to raise instead).
- LiteLLM is an **optional** extra: `openai-agents[litellm]` requires `litellm>=1.83.0`, which is after the compromised releases (PyPI metadata).

**b. Tracing**
- "Tracing is enabled by default" ([tracing docs](https://openai.github.io/openai-agents-python/tracing/)).
- Traces upload to OpenAI, so without an OpenAI key you get 401 tracing errors ([models docs](https://openai.github.io/openai-agents-python/models/)).
- Ways to disable it ([tracing docs](https://openai.github.io/openai-agents-python/tracing/)):
  - `OPENAI_AGENTS_DISABLE_TRACING=1`
  - `set_tracing_disabled(True)`
  - `RunConfig(tracing_disabled=True)`
- `trace_include_sensitive_data` defaults to `True` (same page).

**c. Local context**
- "The context object is not sent to the LLM." Pass it with `Runner.run(..., context=obj)` and read it in tools with `wrapper.context` on a `RunContextWrapper[T]` ([context docs](https://openai.github.io/openai-agents-python/context/)).
- `ToolContext` extends it and adds `tool_name`, `tool_call_id` and `tool_arguments` (same page).
- The decorator exported in 0.24.0 is `function_tool` ([source](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/__init__.py)). The context page's example shows `@tool`, which I did **not** find exported. **UNVERIFIED alias.**

**d. Trajectory**
- `result.new_items` holds `ToolCallItem`, `ToolCallOutputItem` and `MessageOutputItem` ([results docs](https://openai.github.io/openai-agents-python/results/)).
- `ToolCallItem` has a `tool_name` property ([source `items.py`](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/items.py)).
- On Chat Completions, tool calls are converted to `ResponseFunctionToolCall`, which has `.name` and `.arguments` (a JSON string) ([source `chatcmpl_converter.py`](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/models/chatcmpl_converter.py)).
- The docs recommend mapping-safe access because "Raw items can be typed Responses objects or mappings" ([results docs](https://openai.github.io/openai-agents-python/results/)).

**e. Sessions**
- `SQLiteSession(session_id, db_path=":memory:")`. A session without a path is "In-memory database (lost when process ends)". Pass it with `Runner.run(agent, msg, session=session)` ([sessions docs](https://openai.github.io/openai-agents-python/sessions/), [source](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/memory/sqlite_session.py)).
- Alternative: `result.to_input_list()` for manual history.

**f. Loop guard**
- `max_turns`. The default is `DEFAULT_MAX_TURNS = 10` ([source `run_config.py`](https://github.com/openai/openai-agents-python/blob/v0.24.0/src/agents/run_config.py)).
- Exceeding it raises `MaxTurnsExceeded`. `error_handlers={"max_turns": ...}` can return a controlled final output instead ([running agents](https://openai.github.io/openai-agents-python/running_agents/)).

**g. Guardrails**
- `@input_guardrail` returns `GuardrailFunctionOutput(output_info, tripwire_triggered)`. A tripped guardrail raises `InputGuardrailTripwireTriggered` ([guardrails docs](https://openai.github.io/openai-agents-python/guardrails/)).
- The default is `run_in_parallel=True`: the agent "may have already consumed tokens and executed tools before being cancelled". Use `run_in_parallel=False` to block until the guardrail finishes.
- Input guardrails run only on the first agent.

**h. Maturity**
- 0.24.0, released 2026-10-15 (PyPI). Recent minors: 0.21.0 (08-15), 0.22.0 (08-19), 0.23.1 (10-02), 0.24.0 (10-15).
- Policy: "Minor (Y) versions: breaking changes to public interfaces not marked as beta" ([release docs](https://openai.github.io/openai-agents-python/release/)).
- Recent breaking changes: 0.21 requires `openai>=3,<4` and moved to HTTPX2; 0.22 changed several behaviours (same page).
- The 0.24.0 notes list features and fixes only ([GitHub release](https://github.com/openai/openai-agents-python/releases/tag/v0.24.0)).

**i. Dependencies**
- 38 resolved packages.
- Hard dependencies include `mcp`, `starlette`, `websockets`, `pyjwt`, `python-multipart` and `requests` (PyPI `requires_dist`). The resolved set also contains `uvicorn`, `sse-starlette` and `cryptography`.

**k. Estimated LOC**
- ~150–180, including ~10 lines of OpenRouter, Chat Completions and tracing config.

### 3.2 Google ADK (`google-adk`)

**a. OpenRouter**
- Python reaches non-Gemini models through `from google.adk.models.lite_llm import LiteLlm`, installed separately with `pip install "litellm>=1.84"` ([ADK LiteLLM docs](https://adk.dev/agents/models/litellm/)). The page has no OpenRouter example.
- The ADK source does recognise `openrouter/...` model names in a comment ([source `model_name_utils.py`](https://github.com/google/adk-python/blob/main/src/google/adk/utils/model_name_utils.py)). That LiteLLM routes `openrouter/<slug>` is LiteLLM convention. **UNVERIFIED in ADK docs.**
- The native OpenAI connector with `BaseURL` and a Chat Completions option is documented for **Go only** and is "experimental" ([ADK OpenAI page](https://adk.dev/agents/models/openai/)). For Python, the same page says OpenAI models go "through the LiteLLM connector".

**b. Telemetry**
- `opentelemetry-api` and `opentelemetry-sdk` are hard dependencies (PyPI).
- OTLP exporters are configured only when `OTEL_EXPORTER_OTLP_*` env vars are set ([source `telemetry/setup.py`](https://github.com/google/adk-python/blob/main/src/google/adk/telemetry/setup.py)). Nothing is exported by default.

**c. Local context**
- Tools receive `tool_context: ToolContext`. In 2.x, `ToolContext = Context` ([source](https://github.com/google/adk-python/blob/main/src/google/adk/tools/tool_context.py)).
- Tools read and write `tool_context.state[...]`. The `temp:` prefix is "Discarded after the invocation completes". Initial state is set with `create_session(state={...})` ([state docs](https://adk.dev/sessions/state/)).
- **Leak risk:** `{key}` placeholders in an instruction are replaced with `session.state` values "before the instruction is passed to the LLM" (same page). Never template the customer id.

**d. Trajectory**
- Iterate `runner.run_async(user_id=, session_id=, new_message=)` events.
- `event.get_function_calls()` returns items with `.name` and `.args`. `event.get_function_responses()` and `event.is_final_response()` cover results and the final answer ([events docs](https://adk.dev/events/)).

**e. Sessions**
- `InMemorySessionService` ([source](https://github.com/google/adk-python/blob/main/src/google/adk/sessions/in_memory_session_service.py), [state docs](https://adk.dev/sessions/state/)).

**f. Loop guard**
- `RunConfig.max_llm_calls`. Default `_DEFAULT_MAX_LLM_CALLS = 500`, overridable with `ADK_MAX_LLM_CALLS` ([source `run_config.py`](https://github.com/google/adk-python/blob/main/src/google/adk/agents/run_config.py)).

**g. Guardrails**
- Plugins are "the recommended approach" for cross-agent policies. A Before Tool Callback can validate tool calls ([safety docs](https://adk.dev/safety/)).
- There is no built-in prompt-injection guard. The docs give a "Gemini as a Judge" plugin example.

**h. Maturity**
- 2.13.0, released 2026-10-23. 2.9 → 2.13 shipped in about six weeks (PyPI). No status classifier.

**i. Dependencies**
- 48 packages by default, including `fastapi`, `uvicorn`, `google-genai`, `google-auth`, `graphviz`, `watchdog`, `authlib` and `cryptography`.
- 81 with LiteLLM, which adds `boto3`, `tokenizers` and `huggingface-hub`.
- The `extensions` and `all` extras pin `litellm>=1.84,<1.106.3` (PyPI metadata). `google-adk[extensions]` resolves to 161 packages.

**j. Supply chain**
- The ADK LiteLLM page warns: "Unauthorized code was identified in LiteLLM versions 1.82.7 and 1.82.8 on PyPI on March 24, 2026". It tells users of the `eval`/`extensions` extras to update and rotate secrets ([ADK LiteLLM docs](https://adk.dev/agents/models/litellm/)).

**k. Estimated LOC**
- ~200–240, because of async Runner, session service and event plumbing.

### 3.3 Vercel AI SDK for Python (`ai`, vercel-labs/ai-python)

**a. OpenRouter**
- Not mentioned on [ai-python.dev](https://ai-python.dev/) or [ai-python.dev/docs](https://ai-python.dev/docs).
- `get_model` docstring: "When the provider is omitted, the model is routed through Vercel AI Gateway" ([source `models/core/model.py`](https://github.com/vercel-labs/ai-python/blob/main/src/ai/models/core/model.py)).
- The OpenAI provider docstring shows `ai.get_provider("openai", base_url="http://localhost:11434/v1")` ([source `providers/openai/__init__.py`](https://github.com/vercel-labs/ai-python/blob/main/src/ai/providers/openai/__init__.py)). The same pattern with OpenRouter's URL should work. **UNVERIFIED.**
- Both `OpenAIChatCompletionsProtocol` and `OpenAIResponsesProtocol` exist. Which one is the default for a custom base URL is **UNVERIFIED**.
- Providers resolve through the `modelsdotdev` registry.

**b. Telemetry**
- An `ai.experimental_telemetry` package exists, and OTel is an optional extra (`ai[otel]`). I found no default exporter. **UNVERIFIED.**

**c. Local context**
- There is no per-run local context object for tools. `class Context(pydantic.BaseModel): """Everything that goes into the LLM."""` holds model, messages, tools and params ([source `agents/agent.py`](https://github.com/vercel-labs/ai-python/blob/main/src/ai/agents/agent.py)).
- The customer id would have to live in a closure or a `contextvars.ContextVar`.

**d–f. Trajectory, history, loop guard**
- Custom loops subclass `ai.Agent` and override `loop(self, context)`, using `context.keep_running()`, `ai.ToolRunner` and `context.add(...)` ([ai-python.dev](https://ai-python.dev/)).
- I found no max-steps or max-turns parameter in the 0.8.0 source. `keep_running()` only checks whether the last message is an assistant message ([source](https://github.com/vercel-labs/ai-python/blob/main/src/ai/agents/agent.py)). A loop cap has to be written by hand.

**g. Guardrails**
- The hooks module is oriented to human-in-the-loop (`hook`, `resolve_hook`, `defer_hook`). There is no guardrail API.

**h. Maturity**
- 0.8.0, released 2026-09-29. PyPI classifier `Development Status :: 4 - Beta`, and the site says "Now in Beta". Eight releases between 07-30 and 09-29.

**i. Dependencies**
- 13 packages (16 with `[openai]`): `httpx2`, `modelsdotdev`, `pydantic`, `typing-extensions`.

**k. Estimated LOC**
- ~180–230. The loop, call cap and context plumbing are hand-written anyway, so it saves little over plain `openai`.

### 3.4 PydanticAI (`pydantic-ai` / `pydantic-ai-slim`)

**a. OpenRouter (native)**
- Install with `pip install "pydantic-ai-slim[openrouter]"`. Set `OPENROUTER_API_KEY` and use `Agent('openrouter:anthropic/claude-sonnet-4.6')`, or `OpenRouterModel` (`pydantic_ai.models.openrouter`) with `OpenRouterProvider` (`pydantic_ai.providers.openrouter`) ([docs](https://pydantic.dev/docs/ai/models/openrouter/)).
- Optional `app_url`/`app_title`, falling back to `OPENROUTER_APP_URL`/`OPENROUTER_APP_TITLE` ([docs](https://pydantic.dev/docs/ai/models/openrouter/), [source `providers/openrouter.py`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/providers/openrouter.py)).
- Settings: `OpenRouterModelSettings(openrouter_reasoning=..., openrouter_provider={...})`.
- OpenRouter's own docs list PydanticAI as a supported framework ([OpenRouter PydanticAI page](https://openrouter.ai/docs/guides/community/pydantic-ai), [frameworks overview](https://openrouter.ai/docs/guides/community/frameworks-and-integrations-overview)).
- Tool-calling caveat for `anthropic/` models: `tool_choice='required'` together with thinking raises `UserError`. Use `'auto'` ([docs](https://pydantic.dev/docs/ai/models/openrouter/)).

**b. Telemetry**
- `Agent._instrument_default = False` ([source `agent/__init__.py`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/agent/__init__.py)). Nothing is emitted unless you opt in.
- The slim install pulls only `logfire-api` (a no-op shim) and `opentelemetry-api`. It does not pull `logfire` itself.

**c. Local context**
- `Agent(..., deps_type=MyDeps)`, then `agent.run(..., deps=MyDeps(...))`. Tools read `ctx.deps` from a `RunContext[MyDeps]` first parameter ([dependencies docs](https://pydantic.dev/docs/ai/core-concepts/dependencies/)).
- Use `@agent.tool` for tools that take `ctx` and `@agent.tool_plain` for tools that don't.
- **Leak risk:** `TemplateStr('...{{name}}')` renders fields from deps into instructions (same page). Do not template the customer id.
- The docs do not state "deps are never sent". It follows from the design: the `ctx` arg is prepended at call time (`args = [ctx] if self.takes_ctx`) and is not part of the JSON schema ([source `_function_schema.py`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/_function_schema.py)). The spike should print a tool schema to confirm.

**d. Trajectory**
- `result.new_messages()` and `result.all_messages()` ([message history docs](https://pydantic.dev/docs/ai/core-concepts/message-history/)).
- `ToolCallPart` fields are `tool_name: str`, `args: str | dict | None` and `tool_call_id: str`, plus an `args_as_dict()` helper ([source `messages.py`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/messages.py)).
- Use `ModelMessagesTypeAdapter` to serialise transcripts to JSON.

**e. Multi-turn memory**
- `agent.run_sync(msg, message_history=prev)`. The docs example passes `result1.new_messages()` ([message history docs](https://pydantic.dev/docs/ai/core-concepts/message-history/)). For an N-turn CLI, keep `result.all_messages()`.

**f. Loop guard**
- With no limits passed, the default `UsageLimits` has `request_limit` 50. `tool_calls_limit` caps successful tool executions. Exceeding either raises `UsageLimitExceeded` ([agent docs](https://pydantic.dev/docs/ai/core-concepts/agent/), [source `usage.py`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/usage.py)).

**g. Guardrails**
- Not in core. `from pydantic_ai_harness import InputGuardrail`, used as `InputGuardrail(guard=fn, parallel=False)`. A `block` verdict "becomes the response". Raising `InputBlocked` (a `GuardrailError`) fails the run instead ([guardrails docs](https://pydantic.dev/docs/ai/harness/guardrails/)).
- The harness is "on 0.x releases, the API may change between minor releases" (same page).
- PyPI: `pydantic-ai-harness` 0.64.0 (2026-10-31) pins `pydantic-ai-slim==2.64.0` and adds `httpx`.
- Lifecycle hooks such as `before_model_request` also exist ([hooks docs](https://pydantic.dev/docs/ai/core-concepts/hooks/)).
- For this challenge, a plain pre-check function before `agent.run` is simpler and easier to explain.

**h. Maturity**
- 2.64.0, released 2026-10-31. V1 shipped 2025-09-05 and V2.0 on 2026-06-23 (GitHub releases).
- Policy: "We will not intentionally make breaking changes in minor releases" ([version policy](https://github.com/pydantic/pydantic-ai/blob/main/docs/version-policy.md)).
- The cadence is very fast (2.58 → 2.64 between 10-20 and 10-31), so pin the exact version and the lockfile.

**i. Dependencies**
- `pydantic-ai-slim[openrouter]` resolves to 20 packages: `openai`, `pydantic`, `pydantic-graph`, `httpx2`, `genai-prices`, `griffelib`, `opentelemetry-api`, `logfire-api`, ...
- The meta-package `pydantic-ai` pulls `[anthropic,cli,evals,google,logfire,mcp,openai,web]`, which resolves to **95** packages. Do not install it.

**k. Estimated LOC**
- ~130–160.

### 3.5 LangGraph / LangChain

**a. OpenRouter**
- `pip install -U langchain-openrouter`, then `from langchain_openrouter import ChatOpenRouter` with `OPENROUTER_API_KEY`. `bind_tools` is supported, and `create_agent(model="openrouter:<slug>")` works ([LangChain OpenRouter integration](https://docs.langchain.com/oss/python/integrations/chat/openrouter), [OpenRouter LangChain page](https://openrouter.ai/docs/guides/community/langchain)).
- `langchain-openrouter` 0.2.9 (2026-09-22) carries the `Development Status :: 4 - Beta` classifier (PyPI). The alternative is `langchain-openai` 1.7.3 (Stable) with `base_url`.

**b. Telemetry**
- LangSmith tracing turns on with `LANGSMITH_TRACING=true`. An uninstrumented call "will NOT be traced (assuming LANGSMITH_TRACING is not set)" ([LangSmith docs](https://docs.langchain.com/langsmith/trace-with-langchain)).
- `langsmith` is still installed as a dependency.

**c. Local context**
- `create_agent(..., context_schema=Context)`, then `agent.invoke({...}, context=Context(user_id=...))`. Tools take `runtime: ToolRuntime[Context]` and read `runtime.context` ([runtime docs](https://docs.langchain.com/oss/python/langchain/runtime)).
- The page does not state whether context is hidden from the model. Middleware can copy it into the system prompt.

**d. Trajectory**
- `result["messages"]` holds `AIMessage.tool_calls`. This is standard LangChain message types; I did not deep-verify it on a docs page for this note.

**e. Memory**
- `checkpointer=InMemorySaver()` (`langgraph.checkpoint.memory`) plus `config={"configurable": {"thread_id": "1"}}` ([short-term memory docs](https://docs.langchain.com/oss/python/langchain/short-term-memory)).

**f. Loop guard**
- `ModelCallLimitMiddleware(run_limit=..., thread_limit=..., exit_behavior="end"|"error")`. Both limits default to no limit.
- `ToolCallLimitMiddleware(run_limit=..., thread_limit=...)` ([built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)).

**g. Guardrails**
- `PIIMiddleware` and `HumanInTheLoopMiddleware`.
- Custom guardrails use `@before_agent(can_jump_to=["end"])` and return `{"jump_to": "end", ...}` ([guardrails docs](https://docs.langchain.com/oss/python/langchain/guardrails)).

**h. Maturity**
- `langchain` 1.4.8 released 2026-11-02, the day of this research. `langgraph` 1.2.19 released 2026-10-30. Both are stable 1.x with daily or weekly cadence (PyPI).

**i. Dependencies**
- 42–44 packages, including `langsmith`, `langgraph-*`, `orjson`, `zstandard` and `xxhash`.

**k. Estimated LOC**
- ~150–180. More concepts to explain in the README: graph, checkpointer, thread_id, middleware, runtime.

### 3.6 Plain `openai` SDK with a hand-written loop

**a. OpenRouter**
- OpenRouter's quickstart shows the OpenAI Python SDK with `base_url="https://openrouter.ai/api/v1"`, `api_key=<OPENROUTER_API_KEY>`, and optional `extra_headers` `HTTP-Referer` and `X-OpenRouter-Title` ([quickstart](https://openrouter.ai/docs/quickstart)).
- OpenRouter "standardizes the tool calling interface across models and providers" using the OpenAI function-calling shape ([tool calling](https://openrouter.ai/docs/guides/features/tool-calling)).
- Tool-calling rules on the same page:
  - `tools` must be sent on every request, including the follow-up that returns tool results.
  - `parallel_tool_calls` defaults to true for most models.
  - To find tool-capable models, filter with `?supported_parameters=tools`.

**b. Telemetry**
- None; the SDK sends nothing beyond the API calls.

**c–g. Local context, trajectory, memory, loop guard, guardrails**
- All of these are your own code. The customer id lives in a Python object that is never serialised into `messages`.
- The trajectory is the list of `tool_calls` you executed.
- History is your `messages` list, the loop guard is a `for _ in range(MAX_LLM_CALLS)`, and the guardrail is a function called before the loop.

**h. Maturity**
- 3.42.1, released 2026-11-01.
- 3.0.0 (2026-08-12) had one breaking change: "HTTPX2 is now the default HTTP client, and `httpx` is no longer installed automatically" ([GitHub release](https://github.com/openai/openai-python/releases/tag/v3.0.0)). It doesn't matter here.

**i. Dependencies**
- 14 packages.

**k. Estimated LOC**
- ~190–230: loop ~60–80, tool JSON schemas by hand or via pydantic ~40, CLI ~25, trajectory and guard ~30.

### 3.7 Supply chain: LiteLLM 1.82.7 / 1.82.8 (item j)

- **Confirmed** by LiteLLM's own post. Only `litellm==1.82.7` and `litellm==1.82.8` on PyPI were compromised ([LiteLLM security update](https://docs.litellm.ai/blog/security-update-march-2026)):
  - The packages were "live on March 24, 2026 from 10:39 UTC for about 40 minutes before being quarantined by PyPI".
  - The payload was a credential stealer that exfiltrated to `models.litellm.cloud`. 1.82.8 also added `litellm_init.pth`.
  - Safe versions are ≤1.82.6 and the clean 1.83.0+. "These versions have already been removed from PyPI."
- PyPI JSON confirms that 1.82.7 and 1.82.8 are absent, while 1.82.6 (2026-03-22) and 1.83.0 (2026-03-31) are present. The current version is 1.106.6.
- The ADK docs carry the same warning ([ADK LiteLLM docs](https://adk.dev/agents/models/litellm/)).
- Which candidates pull LiteLLM (from PyPI `requires_dist`):

| Candidate | LiteLLM by default? | Optional? |
|---|---|---|
| OpenAI Agents SDK | No | `openai-agents[litellm]` → `litellm>=1.83.0` |
| Google ADK | No (base install) | `[extensions]`, `[all]`, `[test]` → `litellm>=1.84,<1.106.3`. **Required in practice for OpenRouter in Python** |
| Vercel `ai` | No | No |
| PydanticAI | No | No (OpenRouter goes through the `openai` SDK) |
| LangChain / LangGraph | No | No (`langchain-openrouter` uses the `openrouter` SDK) |
| Plain `openai` | No | No |

---

## 4. Gotchas for PydanticAI + OpenRouter (with config snippets)

```toml
# pyproject.toml — pin exactly; do NOT use the `pydantic-ai` meta-package (95 deps incl. logfire, anthropic, google-genai)
dependencies = ["pydantic-ai-slim[openrouter]==2.64.0"]
```

```python
import os
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext, ToolCallPart, UsageLimits, UsageLimitExceeded  # all in pydantic_ai.__all__ (2.64.0 source)

@dataclass
class Deps:                       # local only; never templated into instructions
    verified_customer_id: str | None = None

MODEL = os.environ.get("MODEL", "openrouter:google/gemini-3.8-flash")   # OPENROUTER_API_KEY read by the provider
agent = Agent(MODEL, deps_type=Deps, instructions="...")              # no TemplateStr with deps fields

@agent.tool
def get_orders(ctx: RunContext[Deps]) -> list[dict]:
    """List the verified customer's orders."""
    if ctx.deps.verified_customer_id is None:            # enforcement in code, not in prompt
        return [{"error": "customer not verified"}]
    ...

history = []
deps = Deps()
result = agent.run_sync(user_text, deps=deps, message_history=history,
                        usage_limits=UsageLimits(request_limit=6, tool_calls_limit=8))
history = result.all_messages()                          # docs example uses new_messages(); all_messages() for N turns
calls = [(p.tool_name, p.args_as_dict())
         for m in result.new_messages() for p in getattr(m, "parts", [])
         if isinstance(p, ToolCallPart)]                 # ToolCallPart.part_kind == 'tool-call' (source)
```

1. **Model id is `openrouter:<vendor>/<model>`** ([docs](https://pydantic.dev/docs/ai/models/openrouter/)). The `MODEL` env var should hold the full string. Tool-capable slugs listed by `GET https://openrouter.ai/api/v1/models` on 2026-11-02 include `google/gemini-3.8-flash`, `anthropic/claude-sonnet-5.5` and `deepseek/deepseek-v4.1-flash`. The spike must confirm each one handles tools well.
2. **`request_limit` defaults to 50** ([agent docs](https://pydantic.dev/docs/ai/core-concepts/agent/)). Set your own `UsageLimits` per turn and catch `UsageLimitExceeded` to give a graceful CLI message.
3. **Where the customer id goes:** keep it in `deps`, never in `instructions` or `TemplateStr`. The tool decides "verified or not" from `ctx.deps`, and the verify tool writes `ctx.deps.verified_customer_id` after checking credentials in code. Whether a mutable deps object persists across turns depends on reusing the same `Deps` instance in the CLI, which is plain Python.
4. **Anthropic via OpenRouter:** do not force `tool_choice='required'` while thinking is on, because it raises `UserError` ([docs](https://pydantic.dev/docs/ai/models/openrouter/)).
5. **Guardrail:** for the nice-to-have, a pre-check function before `agent.run` (regex plus an optional small classifier call) avoids depending on `pydantic-ai-harness` (0.x). If you use the harness, pin it to the same version as slim (0.64.0 ↔ 2.64.0).
6. **Deterministic tests:** use `TestModel` / `FunctionModel` (`pydantic_ai.models.test`, `pydantic_ai.models.function`) and `agent.override(model=...)` ([source](https://github.com/pydantic/pydantic-ai/tree/main/pydantic_ai_slim/pydantic_ai/models)). The `models.ALLOW_MODEL_REQUESTS = False` flag blocks accidental real calls in tests. Exact usage is **UNVERIFIED on a docs page**; the names were confirmed in the 2.64.0 source.
7. **Provider routing / fallbacks:** OpenRouter may route a slug to different upstream providers. `OpenRouterModelSettings(openrouter_provider={'order': [...], 'allow_fallbacks': False})` pins the provider if tool-call behaviour varies ([docs](https://pydantic.dev/docs/ai/models/openrouter/)).

---

## 5. Open risks: what the 1-hour spike must confirm

1. **Tool calling end to end for all three models** through `openrouter:` with 5 tools. Check that `ToolCallPart.args` parses for Gemini Flash, Claude Sonnet and DeepSeek, and that parallel tool calls are handled.
2. **The `ctx` parameter is absent from the tool schema.** Inspect the tool definitions sent in the request: run with `FunctionModel` and print `info.function_tools`, or log the request.
3. **The customer id never appears in the request body.** Grep a captured request or `all_messages_json()` for the id across a 3-turn run.
4. **`UsageLimits` behaviour:** confirm that `request_limit=N` stops a deliberately looping tool and that `UsageLimitExceeded` is catchable in the CLI.
5. **Multi-turn:** check that `all_messages()` fed back as `message_history` keeps tool-call/tool-return pairing valid for all three providers. Some providers reject orphaned tool results.
6. **Python 3.12 + `uv sync`** installs cleanly with `pydantic-ai-slim[openrouter]==2.64.0` (resolution checked with `uv pip compile`; an actual install was not run).
7. **Fallback trigger:** if items 1 or 5 fail for a model, switch to the plain `openai` loop (runner-up). The tool functions and the `Deps` dataclass carry over unchanged.

---

## 6. Sources

**PyPI** (versions, dates, `requires_dist`, classifiers via `https://pypi.org/pypi/<pkg>/json`):
- https://pypi.org/project/openai-agents/
- https://pypi.org/project/google-adk/
- https://pypi.org/project/ai/
- https://pypi.org/project/pydantic-ai/
- https://pypi.org/project/pydantic-ai-slim/
- https://pypi.org/project/pydantic-ai-harness/
- https://pypi.org/project/langchain/
- https://pypi.org/project/langgraph/
- https://pypi.org/project/langchain-openrouter/
- https://pypi.org/project/langchain-openai/
- https://pypi.org/project/openai/
- https://pypi.org/project/litellm/

**OpenAI Agents SDK:**
- Docs:
  - https://openai.github.io/openai-agents-python/models/
  - https://openai.github.io/openai-agents-python/tracing/
  - https://openai.github.io/openai-agents-python/context/
  - https://openai.github.io/openai-agents-python/sessions/
  - https://openai.github.io/openai-agents-python/running_agents/
  - https://openai.github.io/openai-agents-python/results/
  - https://openai.github.io/openai-agents-python/guardrails/
  - https://openai.github.io/openai-agents-python/release/
- Release: https://github.com/openai/openai-agents-python/releases/tag/v0.24.0
- Source (checked in the 0.24.0 wheel): `src/agents/{__init__,run_config,items}.py`, `src/agents/memory/sqlite_session.py`, `src/agents/models/{multi_provider,chatcmpl_converter}.py` under https://github.com/openai/openai-agents-python/tree/v0.24.0/src/agents

**Google ADK:**
- Docs:
  - https://adk.dev/agents/models/litellm/
  - https://adk.dev/agents/models/openai/
  - https://adk.dev/sessions/state/
  - https://adk.dev/events/
  - https://adk.dev/safety/
- Source (checked in the 2.13.0 wheel): `agents/run_config.py`, `telemetry/setup.py`, `tools/tool_context.py`, `sessions/in_memory_session_service.py`, `utils/model_name_utils.py` under https://github.com/google/adk-python/tree/main/src/google/adk

**Vercel AI SDK for Python:**
- Docs: https://ai-python.dev/ and https://ai-python.dev/docs
- Source (checked in the 0.8.0 wheel): `models/core/model.py`, `providers/openai/{__init__,provider,protocol}.py`, `agents/agent.py` under https://github.com/vercel-labs/ai-python

**PydanticAI:**
- Docs:
  - https://pydantic.dev/docs/ai/models/openrouter/
  - https://pydantic.dev/docs/ai/core-concepts/dependencies/
  - https://pydantic.dev/docs/ai/core-concepts/message-history/
  - https://pydantic.dev/docs/ai/core-concepts/agent/
  - https://pydantic.dev/docs/ai/core-concepts/hooks/
  - https://pydantic.dev/docs/ai/harness/guardrails/
- Version policy: https://github.com/pydantic/pydantic-ai/blob/main/docs/version-policy.md
- Source (checked in the 2.64.0 wheel): `providers/openrouter.py`, `usage.py`, `messages.py`, `_function_schema.py`, `agent/__init__.py`, `models/{test,function}.py` under https://github.com/pydantic/pydantic-ai/tree/main/pydantic_ai_slim/pydantic_ai

**LangChain / LangGraph:**
- https://docs.langchain.com/oss/python/langchain/runtime
- https://docs.langchain.com/oss/python/langchain/short-term-memory
- https://docs.langchain.com/oss/python/langchain/guardrails
- https://docs.langchain.com/oss/python/langchain/middleware/built-in
- https://docs.langchain.com/oss/python/integrations/chat/openrouter
- https://docs.langchain.com/langsmith/trace-with-langchain

**OpenAI Python SDK:**
- https://github.com/openai/openai-python/releases/tag/v3.0.0

**OpenRouter:**
- https://openrouter.ai/docs/quickstart
- https://openrouter.ai/docs/guides/features/tool-calling
- https://openrouter.ai/docs/api_reference/responses/overview
- https://openrouter.ai/docs/api_reference/responses/basic-usage
- https://openrouter.ai/docs/guides/community/frameworks-and-integrations-overview
- https://openrouter.ai/docs/guides/community/pydantic-ai
- https://openrouter.ai/docs/guides/community/langchain
- https://openrouter.ai/api/v1/models (model slugs, queried 2026-11-02)

**LiteLLM incident:**
- https://docs.litellm.ai/blog/security-update-march-2026
- ADK docs warning (above)
