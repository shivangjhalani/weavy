"""
Run trace helpers — create, update, and persist RunTrace objects.
Also provides EventTracer: a JSONL event stream written live during a run.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from arakne.models.traces import RunTrace, TouchedEdge, TouchedNode, Turn


def _truncate(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[:n] + "…"


def _summarize_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    roles = [str(m.get("role", "unknown")) for m in messages]
    total_chars = sum(len(str(m.get("content") or "")) for m in messages)

    recent_messages: list[dict[str, str]] = []
    for msg in messages[-3:]:
        recent_messages.append({
            "role": str(msg.get("role", "unknown")),
            "content_preview": _truncate(str(msg.get("content") or ""), 160),
        })

    return {
        "message_count": len(messages),
        "roles": roles,
        "content_chars": total_chars,
        "recent_messages": recent_messages,
    }


class EventTracer:
    """Live JSONL event tracer + console printer.

    Writes pretty-printed JSON blocks to runs/<run_id>.jsonl (one blank-line-separated
    block per event, flushed immediately — readable with `tail -f`).
    Also prints a compact human-readable line to stdout for each event.

    Event sequence:
        run_start    — fired once before the loop (mode, input_summary, prompt metadata)
        llm_turn     — model responded (compact input summary, reasoning, text, usage)
        tool_call    — tool about to execute (turn, tool_call_id, name, args)
        tool_result  — tool returned (turn, tool_call_id, name, result, duration_ms)
        tool_error   — tool failed (turn, tool_call_id, name, error)
        run_end      — final event (status, total_usage, completion payload, touched entities)
    """

    def __init__(self, run_id: str, runs_dir: str = "runs") -> None:
        os.makedirs(runs_dir, exist_ok=True)
        self.path = os.path.join(runs_dir, f"{run_id}.jsonl")

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "event": event,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            **payload,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str, indent=2) + "\n\n")
            fh.flush()

    def on_run_start(
        self,
        mode: str,
        input_summary: str,
        prompt_metadata: dict[str, Any],
    ) -> None:
        self._emit("run_start", {
            "mode": mode,
            "input_summary": input_summary,
            "prompt_metadata": prompt_metadata,
        })
        print(f"[run_start] mode={mode} | {input_summary}")

    def on_llm_turn(
        self,
        turn: int,
        input_messages: list[dict[str, Any]],
        reasoning: str | None,
        text: str | None,
        tool_call_count: int,
        usage: dict[str, int],
    ) -> None:
        self._emit("llm_turn", {
            "turn": turn,
            "input_summary": _summarize_messages(input_messages),
            "reasoning": reasoning,
            "text": text,
            "tool_call_count": tool_call_count,
            "usage": usage,
        })
        u = usage
        token_info = f"prompt={u['prompt_tokens']} completion={u['completion_tokens']} reasoning={u['reasoning_tokens']} total={u['total_tokens']}"
        if reasoning:
            print(f"\n[T{turn}] 💭 {_truncate(reasoning)}")
        elif text:
            print(f"\n[T{turn}] 💬 {_truncate(text)}")
        else:
            print(f"\n[T{turn}] ▶ (no text, {tool_call_count} tool call(s))")
        print(f"       tokens: {token_info}")

    def on_tool_call(
        self, turn: int, tool_call_id: str, name: str, args: dict[str, Any]
    ) -> None:
        self._emit("tool_call", {
            "turn": turn,
            "tool_call_id": tool_call_id,
            "tool": name,
            "args": args,
        })
        args_short = _truncate(json.dumps(args, separators=(",", ":")))
        print(f"[T{turn}] → {name}#{tool_call_id}({args_short})")

    def on_tool_result(
        self,
        turn: int,
        tool_call_id: str,
        name: str,
        result: str,
        duration_ms: float,
    ) -> None:
        self._emit("tool_result", {
            "turn": turn,
            "tool_call_id": tool_call_id,
            "tool": name,
            "result": result,
            "duration_ms": round(duration_ms, 1),
        })
        print(f"[T{turn}] ← {name}#{tool_call_id} ({duration_ms:.0f}ms): {_truncate(result, 80)}")

    def on_tool_error(
        self, turn: int, tool_call_id: str | None, name: str, error: str
    ) -> None:
        self._emit("tool_error", {
            "turn": turn,
            "tool_call_id": tool_call_id,
            "tool": name,
            "error": error,
        })
        suffix = f"#{tool_call_id}" if tool_call_id else ""
        print(f"[T{turn}] ✗ {name}{suffix}: {error}")

    def on_run_end(
        self,
        status: str,
        total_turns: int,
        total_usage: dict[str, int],
        error: str | None = None,
        context_limit: int | None = None,
        completion_payload: dict[str, Any] | None = None,
        touched_nodes: list[TouchedNode] | None = None,
        touched_edges: list[TouchedEdge] | None = None,
    ) -> None:
        self._emit("run_end", {
            "status": status,
            "total_turns": total_turns,
            "total_usage": total_usage,
            "context_limit": context_limit,
            "completion_payload": completion_payload,
            "touched_nodes": [node.model_dump() for node in (touched_nodes or [])],
            "touched_edges": [edge.model_dump() for edge in (touched_edges or [])],
            "error": error,
        })
        u = total_usage
        status_icon = "✓" if status == "completed" else "✗"
        prompt = u["prompt_tokens"]
        if context_limit:
            pct = prompt / context_limit * 100
            ctx_str = f"{prompt:,} / {context_limit:,} ({pct:.1f}%)"
        else:
            ctx_str = f"{prompt:,}"
        print(
            f"\n[{status_icon}] {status} | {total_turns} turn(s)"
            f"\n    context: {ctx_str} | output: {u['completion_tokens']:,}"
            f" | reasoning: {u['reasoning_tokens']:,}"
        )
        if error:
            print(f"    error: {error}")


def new_trace(
    mode: Literal["ingestion", "query", "theme"],
    input_summary: str,
) -> RunTrace:
    return RunTrace(
        mode=mode,
        started_at=datetime.now(tz=timezone.utc),
        input_summary=input_summary,
        status="running",
    )


def record_turn(trace: RunTrace, turn: Turn) -> None:
    trace.turns.append(turn)
    trace.total_usage.prompt_tokens += turn.usage.prompt_tokens
    trace.total_usage.completion_tokens += turn.usage.completion_tokens
    trace.total_usage.reasoning_tokens += turn.usage.reasoning_tokens
    trace.total_usage.total_tokens += turn.usage.total_tokens


def finalize_trace(
    trace: RunTrace,
    status: Literal["completed", "failed"],
    completion_payload: dict | None = None,
    error: str | None = None,
) -> RunTrace:
    trace.status = status
    trace.ended_at = datetime.now(tz=timezone.utc)
    if completion_payload is not None:
        trace.completion_payload = completion_payload
    if error is not None:
        trace.error = error
    return trace


def save_trace(trace: RunTrace, run_dir: str) -> str:
    """Persist trace as JSON to run_dir. Returns file path."""
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, f"{trace.run_id}.json")
    with open(path, "w") as f:
        f.write(trace.model_dump_json(indent=2))
    return path
