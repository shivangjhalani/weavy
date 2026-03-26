"""AgentHarness -- manual dispatch loop for litellm function calling.

Per D-06: Roll our own loop for control and instrumentation.
Per D-07: Tools as dict mapping names to callables.
Per D-08: Agent loops until model stops calling tools -- no enforced limit.

Usage:
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"my_tool": my_callable},
        declarations=[my_fn_declaration],
    )
    result = harness.run(system_prompt=prompt_text, user_message="User query here.")
    cost = harness.last_run_cost  # accumulated cost in USD

Optional tracing (injected, not baked in):
    from lifeos.agent.tracer import JsonlTracer
    tracer = JsonlTracer()
    harness = AgentHarness(..., tracer=tracer)
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

import litellm

from lifeos.agent.tracer import Tracer

logger = logging.getLogger(__name__)


class AgentHarness:
    """Manual dispatch loop for litellm function calling.

    All three agent roles (ingest, query, memo) use this same harness
    with different system prompts and tool sets.
    """

    def __init__(
        self,
        model: str,
        tools: dict[str, Callable[..., Any]],
        declarations: list[dict],
        tracer: Tracer | None = None,
        reasoning_effort: str | None = None,
    ):
        """
        Args:
            model: Model name with provider prefix, e.g. "gemini/gemini-2.5-flash".
            tools: Dict mapping tool name to Python callable.
            declarations: List of OpenAI-format tool dicts for the litellm API.
            tracer: Optional Tracer instance for event callbacks. When None (default),
                zero overhead -- no tracer calls are made.
            reasoning_effort: Optional reasoning effort level ("none", "low", "medium",
                "high"). When None, uses the model's default. Maps to litellm's
                reasoning_effort parameter.
        """
        self.model = model
        self.tools = tools
        self.declarations = declarations
        self.tracer = tracer
        self.reasoning_effort = reasoning_effort
        self.last_run_cost: float = 0.0

    def run(self, system_prompt: str, user_message: str) -> str:
        """Run the agent loop and return the final text response.

        Continues dispatching tool calls until the model emits a response
        with no function calls. Accumulates per-call cost in self.last_run_cost.

        Args:
            system_prompt: Role-specific system instruction (loaded from prompts/*.md).
            user_message: The user's input (transcript, question, etc.).

        Returns:
            Final text response from the model as a string.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        turn = 0
        total_tool_calls = 0
        total_cost = 0.0

        if self.tracer:
            self.tracer.on_run_start(
                self.model,
                list(self.tools.keys()),
                datetime.now(timezone.utc).isoformat(),
            )

        # Build completion kwargs
        completion_kwargs: dict[str, Any] = {
            "model": self.model,
            "tools": self.declarations,
            "tool_choice": "auto",
        }
        if self.reasoning_effort is not None:
            completion_kwargs["reasoning_effort"] = self.reasoning_effort

        while True:
            turn += 1

            response = litellm.completion(messages=messages, **completion_kwargs)

            # Track cost (best-effort)
            try:
                cost = litellm.completion_cost(completion_response=response)
                total_cost += cost
            except Exception:
                pass

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # Guard: no message content and no tool calls
            if msg.content is None and not msg.tool_calls:
                logger.warning(
                    "litellm response has no content and no tool_calls (finish_reason=%s).",
                    finish_reason,
                )
                if self.tracer:
                    self.tracer.on_llm_error(turn, "no_content", str(finish_reason))
                raise RuntimeError(
                    f"LLM stopped with finish_reason={finish_reason} and no content. "
                    "The model may have hit a token limit, safety filter, or recitation block."
                )

            tool_calls = msg.tool_calls

            # Extract text for tracer
            response_text = msg.content
            thinking_text = None  # litellm does not expose thinking separately

            if self.tracer:
                self.tracer.on_llm_response(
                    turn,
                    str(finish_reason),
                    len(tool_calls) if tool_calls else 0,
                    thinking_text,
                    response_text,
                )

            # Append assistant message to history
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            if not tool_calls:
                # Model returned no tool calls -- done
                self.last_run_cost = total_cost
                if self.tracer:
                    self.tracer.on_run_end(turn, total_tool_calls, msg.content or "")
                return msg.content or ""

            # Dispatch tool calls
            total_tool_calls += len(tool_calls)
            for tc in tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)

                if self.tracer:
                    self.tracer.on_tool_call(turn, name, args)

                t0 = time.perf_counter()
                try:
                    result = self.tools[name](**args)
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if self.tracer:
                        self.tracer.on_tool_result(turn, name, result, duration_ms, True)
                except Exception as e:
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if self.tracer:
                        self.tracer.on_tool_error(turn, name, str(e))
                    raise

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps({"result": result}),
                })
