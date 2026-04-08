"""
Shared helpers for mode orchestration.
"""

from datetime import datetime, timezone
from pathlib import Path

from falkordb import Graph

from weavy.config import settings
from weavy.models.canonical import ChatMessage
from weavy.models.traces import RunTrace
from weavy.store.system import SystemState
from weavy.store.themes import build_themes_context
from weavy.timefmt import format_agent_timestamp


def _langfuse_enabled() -> bool:
    return bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def fetch_prompt(name: str, variables: dict) -> str:
    """Load a prompt template and compile it with the given variables.

    Checks local prompt files first (weavy/prompts/{name}.txt). Falls back to
    Langfuse only when Langfuse keys are configured and the local file doesn't exist.
    """
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{name}.txt"
    if prompt_path.exists():
        template = prompt_path.read_text()
        for key, value in variables.items():
            template = template.replace("{{" + key + "}}", str(value))
        return template

    if _langfuse_enabled():
        from weavy.langfuse_client import get_langfuse

        prompt = get_langfuse().get_prompt(name, label="production")
        return prompt.compile(**variables)

    raise FileNotFoundError(
        f"Prompt '{name}' not found at {prompt_path} and Langfuse is not enabled."
    )


def build_themed_system_prompt(
    prompt_name: str,
    graph: Graph,
    system_state: SystemState,
    empty_themes_message: str,
    variables: dict | None = None,
) -> str:
    """Build a prompt with the shared time and hot-themes context."""
    prompt_variables = dict(variables or {})
    prompt_variables.update(
        current_time=format_agent_timestamp(
            datetime.now(tz=timezone.utc),
            include_relative=False,
        ),
        themes_context=build_themes_context(
            graph,
            system_state.theme_priority_order,
            system_state.hot_theme_token_budget,
            empty_msg=empty_themes_message,
        ),
    )
    return fetch_prompt(prompt_name, prompt_variables)


def conversation_to_chat_messages(conversation: list[dict]) -> list[ChatMessage]:
    """Convert stored harness messages into persisted chat messages."""
    return [
        ChatMessage(role=message["role"], content=message.get("content") or "")
        for message in conversation
        if message["role"] in ("user", "assistant") and message.get("content")
    ]


def run_post_trace_hooks(
    trace: RunTrace,
    graph: Graph,
    system_state: SystemState,
    completion_text: str,
) -> None:
    """Trigger a theme update after a completed session."""
    if not (trace.status == "completed" and trace.touched_nodes):
        return

    from weavy.modes import theme as theme_mode  # local import avoids circular dep

    theme_mode.run_theme_update(completion_text, trace.touched_nodes, trace.touched_edges)
