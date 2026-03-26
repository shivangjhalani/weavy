"""AgentHarness -- manual dispatch loop for Gemini function calling.

Per D-06: Roll our own loop for control and instrumentation.
Per D-07: Tools as dict mapping names to callables.
Per D-08: Agent loops until model stops calling tools -- no enforced limit.

Usage:
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"my_tool": my_callable},
        declarations=[my_fn_declaration],
    )
    result = harness.run(system_prompt=prompt_text, user_message="User query here.")

Optional tracing (injected, not baked in):
    from lifeos.agent.tracer import JsonlTracer
    tracer = JsonlTracer()
    harness = AgentHarness(..., tracer=tracer)
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from google import genai
from google.genai import types

from lifeos.agent.tracer import Tracer

logger = logging.getLogger(__name__)


class AgentHarness:
    """Manual dispatch loop for Gemini function calling.

    All three agent roles (ingest, query, memo) use this same harness
    with different system prompts and tool sets.
    """

    def __init__(
        self,
        model: str,
        tools: dict[str, Callable[..., Any]],
        declarations: list,
        client: genai.Client | None = None,
        tracer: Tracer | None = None,
        thinking_config: types.ThinkingConfig | None = None,
    ):
        """
        Args:
            model: Gemini model name, e.g. "gemini-2.5-flash".
            tools: Dict mapping tool name to Python callable.
            declarations: List of FunctionDeclaration objects for the Gemini API.
            client: Optional pre-built genai.Client (for testing with mocks).
            tracer: Optional Tracer instance for event callbacks. When None (default),
                zero overhead — no tracer calls are made.
            thinking_config: Optional ThinkingConfig to enable extended thinking.
                When None (default), thinking is not requested from the model.
        """
        self.model = model
        self.tools = tools
        self.declarations = declarations
        self.client = client or genai.Client()
        self.tracer = tracer
        self.thinking_config = thinking_config

    def run(self, system_prompt: str, user_message: str) -> str:
        """Run the agent loop and return the final text response.

        Continues dispatching tool calls until the model emits a response
        with no function calls.

        Args:
            system_prompt: Role-specific system instruction (loaded from prompts/*.md).
            user_message: The user's input (transcript, question, etc.).

        Returns:
            Final text response from the model as a string.
        """
        tool_config = types.Tool(function_declarations=self.declarations)
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "tools": [tool_config],
        }
        if self.thinking_config is not None:
            config_kwargs["thinking_config"] = self.thinking_config

        config = types.GenerateContentConfig(**config_kwargs)
        contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]

        turn = 0
        total_tool_calls = 0

        if self.tracer:
            self.tracer.on_run_start(
                self.model,
                list(self.tools.keys()),
                datetime.now(timezone.utc).isoformat(),
            )

        while True:
            turn += 1

            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            # Guard: empty candidates list
            if not response.candidates:
                if self.tracer:
                    self.tracer.on_llm_error(turn, "no_candidates", "UNKNOWN")
                raise RuntimeError("Gemini returned no candidates — cannot continue agent loop.")

            candidate = response.candidates[0]
            finish_reason = getattr(candidate, "finish_reason", "UNKNOWN")

            # Guard: None content — happens when finish_reason is not STOP
            # (e.g. MAX_TOKENS, SAFETY, RECITATION). Log the reason so the caller knows why.
            if candidate.content is None:
                logger.warning(
                    "Gemini candidate content is None (finish_reason=%s) — stopping agent loop.",
                    finish_reason,
                )
                if self.tracer:
                    self.tracer.on_llm_error(turn, "none_content", str(finish_reason))
                raise RuntimeError(
                    f"Gemini stopped with finish_reason={finish_reason} and no content. "
                    "The model may have hit a token limit, safety filter, or recitation block."
                )

            # Extract thinking text and response text from parts
            thinking_text: str | None = None
            response_text: str | None = None
            if candidate.content.parts:
                thinking_parts = [
                    p for p in candidate.content.parts
                    if hasattr(p, "thought") and p.thought and hasattr(p, "text")
                ]
                if thinking_parts:
                    thinking_text = "\n".join(p.text for p in thinking_parts if p.text)

                text_parts = [
                    p for p in candidate.content.parts
                    if p.text and not (hasattr(p, "thought") and p.thought)
                ]
                if text_parts:
                    response_text = "\n".join(p.text for p in text_parts)

            # Check ALL parts for function calls (not just parts[0] — Pitfall 4)
            fc_parts = [p for p in candidate.content.parts if p.function_call]

            if self.tracer:
                self.tracer.on_llm_response(
                    turn,
                    str(finish_reason),
                    len(fc_parts),
                    thinking_text,
                    response_text,
                )

            # Append model response to conversation history
            contents.append(candidate.content)

            if not fc_parts:
                # Model returned no tool calls — it is done
                if self.tracer:
                    self.tracer.on_run_end(turn, total_tool_calls, response.text or "")
                return response.text

            # Dispatch all function calls in this turn and collect responses
            total_tool_calls += len(fc_parts)
            response_parts = []
            for part in fc_parts:
                fc = part.function_call

                if self.tracer:
                    self.tracer.on_tool_call(turn, fc.name, dict(fc.args))

                t0 = time.perf_counter()
                try:
                    result = self.tools[fc.name](**fc.args)
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if self.tracer:
                        self.tracer.on_tool_result(turn, fc.name, result, duration_ms, True)
                except Exception as e:
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if self.tracer:
                        self.tracer.on_tool_error(turn, fc.name, str(e))
                    raise

                # REQUIRED — Pitfall 3: fc.id must be echoed in FunctionResponse for SDK mapping.
                # types.Part.from_function_response() does not accept `id` in this SDK version;
                # use types.Part(function_response=types.FunctionResponse(...)) directly.
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                            id=fc.id,
                        )
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
