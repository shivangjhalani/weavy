"""Tracer protocol for AgentHarness — zero-overhead when disabled.

Tracer base class has all no-op methods. JsonlTracer writes full-fidelity
JSONL to a file in ./traces/ (one JSON line per event, appended immediately).

Injection pattern:
    tracer = JsonlTracer()  # created in ingest.py when --verbose
    harness = AgentHarness(..., tracer=tracer)

Harness only imports Tracer (base) — never JsonlTracer. Caller is responsible
for creating the right implementation and injecting it.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Tracer:
    """No-op tracer base class. All methods are silent pass-throughs.

    When tracer=None is set on AgentHarness, no code path hits these methods.
    When tracer=Tracer() is passed explicitly, calls succeed with zero output.
    """

    def on_run_start(self, model: str, tools: list[str], timestamp: str) -> None:
        pass

    def on_llm_response(
        self,
        turn: int,
        finish_reason: str,
        tool_call_count: int,
        thinking: str | None,
        text: str | None,
    ) -> None:
        pass

    def on_llm_error(self, turn: int, error_type: str, finish_reason: str) -> None:
        pass

    def on_tool_call(self, turn: int, tool_name: str, args: dict) -> None:
        pass

    def on_tool_result(
        self,
        turn: int,
        tool_name: str,
        result: Any,
        duration_ms: float,
        success: bool,
    ) -> None:
        pass

    def on_tool_error(self, turn: int, tool_name: str, exception: str) -> None:
        pass

    def on_run_end(self, total_turns: int, total_tool_calls: int, final_text: str) -> None:
        pass


class JsonlTracer(Tracer):
    """Full-fidelity JSONL tracer — one JSON line per event, appended to file.

    File is created in traces_dir on init. Each write opens in append mode
    and flushes immediately so the file is readable mid-run.

    File naming: {iso_timestamp}_{uuid4_prefix}.jsonl
    e.g. 2025-01-01T12-00-00Z_a3f7b2c1.jsonl
    """

    def __init__(self, traces_dir: Path = Path("./traces")) -> None:
        self.traces_dir = traces_dir
        self.traces_dir.mkdir(parents=True, exist_ok=True)

        # Build filename: sanitize ISO timestamp colons for filesystem safety
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        uid = str(uuid.uuid4()).split("-")[0]  # 8-char prefix
        self.trace_file = self.traces_dir / f"{ts}_{uid}.jsonl"

    def _write(self, event: str, payload: dict) -> None:
        """Append one JSONL line to the trace file."""
        record = {
            "event": event,
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.trace_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()

    def on_run_start(self, model: str, tools: list[str], timestamp: str) -> None:
        self._write("run_start", {"model": model, "tools": tools, "timestamp": timestamp})

    def on_llm_response(
        self,
        turn: int,
        finish_reason: str,
        tool_call_count: int,
        thinking: str | None,
        text: str | None,
    ) -> None:
        self._write(
            "llm_response",
            {
                "turn": turn,
                "finish_reason": finish_reason,
                "tool_call_count": tool_call_count,
                "thinking": thinking,
                "text": text,
            },
        )

    def on_llm_error(self, turn: int, error_type: str, finish_reason: str) -> None:
        self._write(
            "llm_error",
            {"turn": turn, "error_type": error_type, "finish_reason": finish_reason},
        )

    def on_tool_call(self, turn: int, tool_name: str, args: dict) -> None:
        self._write("tool_call", {"turn": turn, "tool_name": tool_name, "args": args})

    def on_tool_result(
        self,
        turn: int,
        tool_name: str,
        result: Any,
        duration_ms: float,
        success: bool,
    ) -> None:
        self._write(
            "tool_result",
            {
                "turn": turn,
                "tool_name": tool_name,
                "result": result,
                "duration_ms": duration_ms,
                "success": success,
            },
        )

    def on_tool_error(self, turn: int, tool_name: str, exception: str) -> None:
        self._write(
            "tool_error",
            {"turn": turn, "tool_name": tool_name, "exception": exception},
        )

    def on_run_end(self, total_turns: int, total_tool_calls: int, final_text: str) -> None:
        self._write(
            "run_end",
            {
                "total_turns": total_turns,
                "total_tool_calls": total_tool_calls,
                "final_text": final_text,
            },
        )
