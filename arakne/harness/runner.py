"""
Agent harness runner — one loop engine shared by ingestion, query, and theme modes.
Implemented in Phase 4.
"""

import json
from datetime import datetime, timezone
from typing import Any, Literal

import litellm
from falkordb import Graph

from arakne.config import settings
from arakne.harness import registry as reg
from arakne.harness.tracing import EventTracer, finalize_trace, new_trace, record_turn
from arakne.models.traces import RunTrace, ToolCall, Turn, TurnUsage


def _usage_dict(trace: RunTrace) -> dict[str, int]:
    u = trace.total_usage
    return {
        "prompt_tokens": u.prompt_tokens,
        "completion_tokens": u.completion_tokens,
        "reasoning_tokens": u.reasoning_tokens,
        "total_tokens": u.total_tokens,
    }


def run(
    mode: Literal["ingestion", "query", "theme"],
    system_prompt: str,
    initial_messages: list[dict[str, Any]],
    allowed_tools: list[str],
    completion_tool: str,  # noqa: ARG001 — reserved for validation in future phases
    run_context: dict[str, Any],
    graph: Graph,
) -> RunTrace:
    """
    Execute an agentic loop until the mode's completion tool is called.
    Returns the completed RunTrace.
    """
    input_summary = run_context.get("input_summary", "")
    trace = new_trace(mode, input_summary)
    ctx = reg.ToolContext(graph=graph, trace=trace)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *initial_messages,
    ]
    tool_definitions = reg.get_tool_definitions(allowed_tools)
    turn_number = 0
    tracer = EventTracer(trace.run_id)

    context_limit: int | None = None
    try:
        info = litellm.get_model_info(settings.GEMINI_MODEL)
        context_limit = info.get("max_input_tokens") or None
    except Exception:
        pass

    while True:
        turn_number += 1
        turn_ts = datetime.now(tz=timezone.utc)

        # --- Call model ---
        try:
            response = litellm.completion(
                model=settings.GEMINI_MODEL,
                messages=messages,
                tools=tool_definitions,
                tool_choice="auto",
                reasoning_effort=settings.REASONING_EFFORT,
            )
        except Exception as e:
            err = f"Model call failed: {e}"
            tracer.on_run_end("failed", turn_number, _usage_dict(trace), error=err, context_limit=context_limit)
            finalize_trace(trace, "failed", error=err)
            return trace

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []

        # --- Build turn usage from response ---
        usage = getattr(response, "usage", None)
        turn_usage = TurnUsage()
        if usage:
            turn_usage.prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            turn_usage.completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            turn_usage.total_tokens = getattr(usage, "total_tokens", 0) or 0
            details = getattr(usage, "completion_tokens_details", None)
            if details and isinstance(details, dict):
                turn_usage.reasoning_tokens = details.get("reasoning_tokens", 0) or 0
            elif details:
                turn_usage.reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

        # --- Start building this turn ---
        reasoning = getattr(message, "reasoning_content", None)
        turn = Turn(
            turn_number=turn_number,
            reasoning_content=reasoning,
            text_content=message.content,
            usage=turn_usage,
            timestamp=turn_ts,
        )

        tracer.on_llm_turn(
            turn=turn_number,
            reasoning=reasoning,
            text=message.content,
            tool_call_count=len(tool_calls),
            usage={
                "prompt_tokens": turn_usage.prompt_tokens,
                "completion_tokens": turn_usage.completion_tokens,
                "reasoning_tokens": turn_usage.reasoning_tokens,
                "total_tokens": turn_usage.total_tokens,
            },
        )

        if not tool_calls:
            record_turn(trace, turn)
            tracer.on_run_end(
                status="failed",
                total_turns=turn_number,
                total_usage={
                    "prompt_tokens": trace.total_usage.prompt_tokens + turn_usage.prompt_tokens,
                    "completion_tokens": trace.total_usage.completion_tokens + turn_usage.completion_tokens,
                    "reasoning_tokens": trace.total_usage.reasoning_tokens + turn_usage.reasoning_tokens,
                    "total_tokens": trace.total_usage.total_tokens + turn_usage.total_tokens,
                },
                error="Model stopped without calling a completion tool.",
                context_limit=context_limit,
            )
            finalize_trace(
                trace, "failed", error="Model stopped without calling a completion tool."
            )
            return trace

        # Append assistant message (with tool_calls) to conversation history
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # --- Process each tool call ---
        for tc in tool_calls:
            tool_name = tc.function.name
            tool_call_id = tc.id
            called_at = datetime.now(tz=timezone.utc)

            # Resolve tool
            entry = reg.REGISTRY.get(tool_name)
            if entry is None:
                err = f"Unknown tool '{tool_name}'."
                tracer.on_tool_error(turn_number, tool_name, err)
                tc_record = ToolCall(
                    tool_name=tool_name, args={}, result=None, error=err, called_at=called_at
                )
                turn.tool_calls.append(tc_record)
                record_turn(trace, turn)
                tracer.on_run_end("failed", turn_number, _usage_dict(trace), error=err, context_limit=context_limit)
                finalize_trace(trace, "failed", error=err)
                return trace

            # Parse args
            args_dict: dict[str, Any] = {}
            try:
                args_dict = json.loads(tc.function.arguments or "{}")
                params = entry.input_model(**args_dict)
            except Exception as e:
                err = f"Invalid arguments for '{tool_name}': {e}"
                tracer.on_tool_error(turn_number, tool_name, err)
                tc_record = ToolCall(
                    tool_name=tool_name,
                    args=args_dict,
                    result=None,
                    error=err,
                    called_at=called_at,
                )
                turn.tool_calls.append(tc_record)
                record_turn(trace, turn)
                tracer.on_run_end("failed", turn_number, _usage_dict(trace), error=err, context_limit=context_limit)
                finalize_trace(trace, "failed", error=err)
                return trace

            # Execute tool
            tracer.on_tool_call(turn_number, tool_name, args_dict)
            t0 = datetime.now(tz=timezone.utc).timestamp()
            try:
                result = entry.fn(params, ctx)
            except Exception as e:
                err = f"Tool '{tool_name}' raised: {e}"
                duration_ms = (datetime.now(tz=timezone.utc).timestamp() - t0) * 1000
                tracer.on_tool_error(turn_number, tool_name, err)
                tc_record = ToolCall(
                    tool_name=tool_name,
                    args=args_dict,
                    result=None,
                    error=err,
                    called_at=called_at,
                )
                turn.tool_calls.append(tc_record)
                record_turn(trace, turn)
                tracer.on_run_end("failed", turn_number, _usage_dict(trace), error=err, context_limit=context_limit)
                finalize_trace(trace, "failed", error=err)
                return trace

            duration_ms = (datetime.now(tz=timezone.utc).timestamp() - t0) * 1000

            # Serialize result for conversation history
            result_str = (
                result.model_dump_json()
                if hasattr(result, "model_dump_json")
                else json.dumps(result)
            )

            tracer.on_tool_result(turn_number, tool_name, result_str, duration_ms)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call_id, "content": result_str}
            )
            turn.tool_calls.append(
                ToolCall(
                    tool_name=tool_name,
                    args=args_dict,
                    result=result_str,
                    called_at=called_at,
                ),
            )

            if entry.is_completion:
                record_turn(trace, turn)
                trace.conversation = [m for m in messages if m["role"] != "system"]
                finalize_trace(trace, "completed")
                tracer.on_run_end("completed", turn_number, _usage_dict(trace), context_limit=context_limit)
                return trace

        # Turn complete (no completion tool yet) — record and loop
        record_turn(trace, turn)
