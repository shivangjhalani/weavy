"""
Run trace helpers — create, update, and persist RunTrace objects.
Also provides EventTracer: a JSONL event stream written live during a run.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from arakne.models.traces import RunTrace, ToolCall, TouchedEdge, TouchedNode, Turn


def _truncate(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[:n] + "…"


class EventTracer:
    """Live JSONL event tracer + console printer.

    Writes pretty-printed JSON blocks to runs/<run_id>.jsonl (one blank-line-separated
    block per event, flushed immediately — readable with `tail -f`).
    Also prints a compact human-readable line to stdout for each event.

    Event sequence per turn:
        llm_turn     — model responded (reasoning + text + usage)
        tool_call    — tool about to execute (turn, name, args)
        tool_result  — tool returned (turn, name, result, duration_ms)
        tool_error   — tool failed (turn, name, error)
        run_end      — final event (status, total_usage, error if any)
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

    def on_llm_turn(
        self,
        turn: int,
        reasoning: str | None,
        text: str | None,
        tool_call_count: int,
        usage: dict[str, int],
    ) -> None:
        self._emit("llm_turn", {
            "turn": turn,
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

    def on_tool_call(self, turn: int, name: str, args: dict[str, Any]) -> None:
        self._emit("tool_call", {"turn": turn, "tool": name, "args": args})
        args_short = _truncate(json.dumps(args, separators=(",", ":")))
        print(f"[T{turn}] → {name}({args_short})")

    def on_tool_result(self, turn: int, name: str, result: str, duration_ms: float) -> None:
        self._emit("tool_result", {
            "turn": turn, "tool": name, "result": result, "duration_ms": round(duration_ms, 1)
        })
        print(f"[T{turn}] ← {name} ({duration_ms:.0f}ms): {_truncate(result, 80)}")

    def on_tool_error(self, turn: int, name: str, error: str) -> None:
        self._emit("tool_error", {"turn": turn, "tool": name, "error": error})
        print(f"[T{turn}] ✗ {name}: {error}")

    def on_run_end(
        self,
        status: str,
        total_turns: int,
        total_usage: dict[str, int],
        error: str | None = None,
        context_limit: int | None = None,
    ) -> None:
        self._emit("run_end", {
            "status": status,
            "total_turns": total_turns,
            "total_usage": total_usage,
            "context_limit": context_limit,
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


def record_tool_call(trace: RunTrace, call: ToolCall) -> None:
    trace.tool_calls.append(call)


def record_touched_node(
    trace: RunTrace,
    node_id: str,
    action: Literal["created", "updated", "deleted"],
) -> None:
    trace.touched_nodes.append(TouchedNode(node_id=node_id, action=action))


def record_touched_edge(
    trace: RunTrace,
    edge_id: str,
    action: Literal["created", "updated", "deleted"],
) -> None:
    trace.touched_edges.append(TouchedEdge(edge_id=edge_id, action=action))


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
