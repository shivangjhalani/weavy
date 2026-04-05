"""
Agent harness runner — one loop engine shared by ingestion, query, and theme modes.
"""

import json
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal

import litellm
from falkordb import Graph

from arakne.config import settings
from arakne.harness import registry as reg
from arakne.harness.tracing import RunTracer, finalize_trace, new_trace, record_turn
from arakne.models.traces import RunTrace, ToolCall, Turn, TurnUsage

_MAX_COMPLETION_NUDGES = 1


@lru_cache(maxsize=None)
def _get_context_limit(model: str) -> int | None:
    try:
        info = litellm.get_model_info(model)
    except Exception:
        return None
    return info.get("max_input_tokens") or None


def _finalize_failed_run(
    trace: RunTrace,
    tracer: RunTracer,
    turn_number: int,
    error: str,
    context_limit: int | None,
    turn: Turn | None = None,
) -> RunTrace:
    if turn is not None:
        record_turn(trace, turn)
    tracer.end_turn(None)
    finalize_trace(trace, "failed", error=error)
    tracer.finalize(
        "failed",
        turn_number,
        trace.total_usage,
        None,
        trace.touched_nodes,
        trace.touched_edges,
        error=error,
        context_limit=context_limit,
    )
    return trace


def _append_tool_call_error(
    turn: Turn,
    tool_name: str,
    args: dict[str, Any],
    error: str,
    called_at: datetime,
) -> None:
    turn.tool_calls.append(
        ToolCall(
            tool_name=tool_name,
            args=args,
            result=None,
            error=error,
            called_at=called_at,
        )
    )


def _build_turn_usage(usage_raw: Any) -> TurnUsage:
    usage = TurnUsage()
    if not usage_raw:
        return usage

    usage.prompt_tokens = getattr(usage_raw, "prompt_tokens", 0) or 0
    usage.completion_tokens = getattr(usage_raw, "completion_tokens", 0) or 0
    usage.total_tokens = getattr(usage_raw, "total_tokens", 0) or 0
    details = getattr(usage_raw, "completion_tokens_details", None)
    if isinstance(details, dict):
        usage.reasoning_tokens = details.get("reasoning_tokens", 0) or 0
    elif details is not None:
        usage.reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0
    return usage


def run(
    mode: Literal["ingestion", "query", "theme"],
    system_prompt: str,
    initial_messages: list[dict[str, Any]],
    allowed_tools: list[str],
    run_context: dict[str, Any],
    graph: Graph,
    session_id: str | None = None,
    parent_observation: Any = None,
) -> RunTrace:
    """
    Execute an agentic loop until the mode's completion tool is called.
    Returns the completed RunTrace.
    """
    input_summary = run_context.get("input_summary", "")
    trace = new_trace(mode, input_summary)
    tracer = RunTracer(
        trace.run_id, mode, input_summary,
        session_id=session_id, parent_observation=parent_observation,
    )
    ctx = reg.ToolContext(graph=graph, trace=trace)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *initial_messages,
    ]
    tool_definitions = reg.get_tool_definitions(allowed_tools)
    turn_number = 0
    completion_nudges = 0

    context_limit = _get_context_limit(settings.GEMINI_MODEL)

    while True:
        turn_number += 1
        turn_ts = datetime.now(tz=timezone.utc)
        input_messages_snapshot = [dict(m) for m in messages]

        tracer.start_turn(turn_number, len(messages))

        # --- Call model ---
        tracer.prepare_llm_call()
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
            return _finalize_failed_run(
                trace, tracer, turn_number, err, context_limit
            )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []

        # --- Build turn usage ---
        turn_usage = _build_turn_usage(getattr(response, "usage", None))

        reasoning = getattr(message, "reasoning_content", None)
        serialized_tool_calls = [
            {"id": tc.id, "name": tc.function.name, "args": tc.function.arguments}
            for tc in tool_calls
        ]

        tracer.record_llm_response(
            turn_number=turn_number,
            input_messages=input_messages_snapshot,
            text_content=message.content,
            reasoning_content=reasoning,
            tool_calls=serialized_tool_calls,
            usage=turn_usage,
        )

        turn = Turn(
            turn_number=turn_number,
            input_messages=input_messages_snapshot,
            reasoning_content=reasoning,
            text_content=message.content,
            usage=turn_usage,
            timestamp=turn_ts,
        )

        if not tool_calls:
            record_turn(trace, turn)
            if message.content and completion_nudges < _MAX_COMPLETION_NUDGES:
                completion_nudges += 1
                tracer.end_turn(message.content)
                messages.append({"role": "assistant", "content": message.content})
                messages.append({
                    "role": "user",
                    "content": (
                        "You must call the completion tool to finish. "
                        "Do not respond with plain text — call deliver_response "
                        "(or the appropriate completion tool for this mode) now."
                    ),
                })
                continue

            err = "Model stopped without calling a completion tool."
            return _finalize_failed_run(
                trace, tracer, turn_number, err, context_limit
            )

        # Append assistant message with tool_calls to conversation history
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
                tracer.record_tool_error(turn_number, tool_call_id, tool_name, {}, err)
                _append_tool_call_error(turn, tool_name, {}, err, called_at)
                return _finalize_failed_run(
                    trace, tracer, turn_number, err, context_limit, turn=turn
                )

            # Parse args
            args_dict: dict[str, Any] = {}
            try:
                args_dict = json.loads(tc.function.arguments or "{}")
                params = entry.input_model(**args_dict)
            except Exception as e:
                err = f"Invalid arguments for '{tool_name}': {e}"
                tracer.record_tool_error(turn_number, tool_call_id, tool_name, args_dict, err)
                _append_tool_call_error(turn, tool_name, args_dict, err, called_at)
                return _finalize_failed_run(
                    trace, tracer, turn_number, err, context_limit, turn=turn
                )

            # Execute tool
            t0 = datetime.now(tz=timezone.utc).timestamp()
            try:
                result = entry.fn(params, ctx)
            except Exception as e:
                err = f"Tool '{tool_name}' raised: {e}"
                tracer.record_tool_error(turn_number, tool_call_id, tool_name, args_dict, err)
                _append_tool_call_error(turn, tool_name, args_dict, err, called_at)
                return _finalize_failed_run(
                    trace, tracer, turn_number, err, context_limit, turn=turn
                )

            duration_ms = (datetime.now(tz=timezone.utc).timestamp() - t0) * 1000
            result_str = (
                result.model_dump_json()
                if hasattr(result, "model_dump_json")
                else json.dumps(result)
            )

            tracer.record_tool_call(
                turn_number, tool_call_id, tool_name, args_dict, result_str, duration_ms
            )
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
                tracer.end_turn(message.content)
                tracer.finalize(
                    "completed", turn_number, trace.total_usage,
                    trace.completion_payload, trace.touched_nodes, trace.touched_edges,
                    context_limit=context_limit,
                )
                return trace

        # Turn complete — record and loop
        tracer.end_turn(message.content)
        record_turn(trace, turn)
