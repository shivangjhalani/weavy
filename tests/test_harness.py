"""Unit tests for AgentHarness — mocked litellm, no live API calls."""
import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Mock helpers — minimal objects matching litellm ModelResponse shape
# ---------------------------------------------------------------------------

class MockFunction:
    """Mimics litellm tool call function with .name and .arguments (JSON string)."""

    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = json.dumps(arguments)


class MockToolCall:
    """Mimics litellm ChatCompletionMessageToolCall."""

    def __init__(self, name: str, args: dict, call_id: str = "call-001"):
        self.id = call_id
        self.type = "function"
        self.function = MockFunction(name, args)


class MockMessage:
    """Mimics litellm message with .content, .tool_calls, .role."""

    def __init__(self, content: str | None = None, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls
        self.role = "assistant"


class MockChoice:
    """Mimics litellm choice with .message, .finish_reason."""

    def __init__(self, message: MockMessage, finish_reason: str = "stop"):
        self.message = message
        self.finish_reason = finish_reason


class MockModelResponse:
    """Mimics litellm ModelResponse with .choices."""

    def __init__(self, choices: list[MockChoice]):
        self.choices = choices
        # For completion_cost mock
        self._hidden_params = {"response_cost": 0.001}
        self.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)


def make_text_response(text: str) -> MockModelResponse:
    """Helper: response with text content and no tool calls."""
    msg = MockMessage(content=text)
    return MockModelResponse(choices=[MockChoice(msg, "stop")])


def make_tc_response(name: str, args: dict, call_id: str = "call-001") -> MockModelResponse:
    """Helper: response with a single tool call."""
    tc = MockToolCall(name, args, call_id)
    msg = MockMessage(content=None, tool_calls=[tc])
    return MockModelResponse(choices=[MockChoice(msg, "tool_calls")])


def make_multi_tc_response(tool_calls: list[tuple[str, dict, str]]) -> MockModelResponse:
    """Helper: response with multiple tool calls."""
    tcs = [MockToolCall(name, args, cid) for name, args, cid in tool_calls]
    msg = MockMessage(content=None, tool_calls=tcs)
    return MockModelResponse(choices=[MockChoice(msg, "tool_calls")])


def make_no_content_response(finish_reason: str = "MAX_TOKENS") -> MockModelResponse:
    """Helper: response with no content and no tool_calls (error condition)."""
    msg = MockMessage(content=None, tool_calls=None)
    return MockModelResponse(choices=[MockChoice(msg, finish_reason)])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_harness_instantiation():
    """AgentHarness accepts model, tools, declarations (no client param), has last_run_cost=0.0."""
    from lifeos.agent.harness import AgentHarness

    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={},
        declarations=[],
    )
    assert harness.model == "gemini/gemini-2.5-flash"
    assert not hasattr(harness, "budget")
    assert harness.last_run_cost == 0.0
    assert not hasattr(harness, "client")


@patch("lifeos.agent.harness.litellm")
def test_harness_text_only_response(mock_litellm):
    """harness.run returns the text when model replies with no tool calls."""
    from lifeos.agent.harness import AgentHarness

    mock_litellm.completion.return_value = make_text_response("The answer is 42.")
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(model="gemini/gemini-2.5-flash", tools={}, declarations=[])
    result = harness.run(system_prompt="You are helpful.", user_message="What is the answer?")
    assert result == "The answer is 42."


@patch("lifeos.agent.harness.litellm")
def test_harness_dispatches_tool_call(mock_litellm):
    """harness.run dispatches to the registered tool callable when model returns a tool call."""
    from lifeos.agent.harness import AgentHarness

    tool_called_with = {}

    def my_tool(x: int, y: int) -> str:
        tool_called_with["x"] = x
        tool_called_with["y"] = y
        return "tool-result"

    mock_litellm.completion.side_effect = [
        make_tc_response("my_tool", {"x": 5, "y": 10}, "call-abc"),
        make_text_response("Done!"),
    ]
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"my_tool": my_tool},
        declarations=[],
    )
    result = harness.run(system_prompt="Use tools.", user_message="Add numbers.")
    assert result == "Done!"
    assert tool_called_with["x"] == 5
    assert tool_called_with["y"] == 10


@patch("lifeos.agent.harness.litellm")
def test_harness_tool_receives_correct_kwargs(mock_litellm):
    """Tool callable receives the exact kwargs from JSON-parsed arguments."""
    from lifeos.agent.harness import AgentHarness

    captured = {}

    def capture_tool(**kwargs):
        captured.update(kwargs)
        return "captured"

    mock_litellm.completion.side_effect = [
        make_tc_response("capture_tool", {"alpha": "hello", "beta": 99}, "call-xyz"),
        make_text_response("Done."),
    ]
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"capture_tool": capture_tool},
        declarations=[],
    )
    harness.run(system_prompt="Use tools.", user_message="Test kwargs.")
    assert captured == {"alpha": "hello", "beta": 99}


@patch("lifeos.agent.harness.litellm")
def test_harness_tool_role_message_format(mock_litellm):
    """After tool dispatch, messages list contains role:tool dict with tool_call_id and name."""
    from lifeos.agent.harness import AgentHarness

    def my_tool(q: str) -> str:
        return f"result for {q}"

    mock_litellm.completion.side_effect = [
        make_tc_response("my_tool", {"q": "test"}, "call-ID-123"),
        make_text_response("Final answer."),
    ]
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"my_tool": my_tool},
        declarations=[],
    )
    harness.run(system_prompt=".", user_message="test")

    # Inspect the second call's messages — should include a tool role message
    second_call_messages = mock_litellm.completion.call_args_list[1][1]["messages"]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    tool_msg = tool_msgs[0]
    assert tool_msg["tool_call_id"] == "call-ID-123"
    assert tool_msg["name"] == "my_tool"


@patch("lifeos.agent.harness.litellm")
def test_harness_iterates_all_parts(mock_litellm):
    """Harness iterates ALL tool calls in a response, not just the first."""
    from lifeos.agent.harness import AgentHarness

    calls_dispatched = []

    def tool_a(val: str) -> str:
        calls_dispatched.append(("a", val))
        return "a-result"

    def tool_b(val: str) -> str:
        calls_dispatched.append(("b", val))
        return "b-result"

    mock_litellm.completion.side_effect = [
        make_multi_tc_response([
            ("tool_a", {"val": "first"}, "call-1"),
            ("tool_b", {"val": "second"}, "call-2"),
        ]),
        make_text_response("all done"),
    ]
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"tool_a": tool_a, "tool_b": tool_b},
        declarations=[],
    )
    result = harness.run(system_prompt=".", user_message="run both")
    assert result == "all done"
    assert ("a", "first") in calls_dispatched
    assert ("b", "second") in calls_dispatched


@patch("lifeos.agent.harness.litellm")
def test_harness_runs_until_model_stops(mock_litellm):
    """Harness runs tool calls until model returns text-only response (no budget limit)."""
    from lifeos.agent.harness import AgentHarness

    call_count = 0

    def counting_tool(n: int) -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{n}"

    # Model calls tool 5 times before returning text
    responses = [make_tc_response("counting_tool", {"n": i}, f"call-{i}") for i in range(5)]
    responses.append(make_text_response("Done after 5 tool calls."))
    mock_litellm.completion.side_effect = responses
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"counting_tool": counting_tool},
        declarations=[],
    )
    result = harness.run(system_prompt=".", user_message="call tools many times")
    assert result == "Done after 5 tool calls."
    assert call_count == 5, f"Expected 5 tool calls, got {call_count}"


@patch("lifeos.agent.harness.litellm")
def test_harness_returns_string(mock_litellm):
    """harness.run always returns a string."""
    from lifeos.agent.harness import AgentHarness

    mock_litellm.completion.return_value = make_text_response("response text")
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(model="gemini/gemini-2.5-flash", tools={}, declarations=[])
    result = harness.run(system_prompt=".", user_message=".")
    assert isinstance(result, str)


@patch("lifeos.agent.harness.litellm")
def test_harness_raises_on_no_content(mock_litellm):
    """harness.run raises RuntimeError when message has no content and no tool_calls."""
    from lifeos.agent.harness import AgentHarness

    mock_litellm.completion.return_value = make_no_content_response("MAX_TOKENS")
    mock_litellm.completion_cost.return_value = 0.001
    harness = AgentHarness(model="gemini/gemini-2.5-flash", tools={}, declarations=[])
    with pytest.raises(RuntimeError, match="finish_reason=MAX_TOKENS"):
        harness.run(system_prompt=".", user_message=".")


@patch("lifeos.agent.harness.litellm")
def test_harness_cost_tracking(mock_litellm):
    """last_run_cost accumulates cost across all turns."""
    from lifeos.agent.harness import AgentHarness

    def dummy_tool() -> str:
        return "ok"

    mock_litellm.completion.side_effect = [
        make_tc_response("dummy_tool", {}, "call-1"),
        make_text_response("Done."),
    ]
    mock_litellm.completion_cost.return_value = 0.005
    harness = AgentHarness(
        model="gemini/gemini-2.5-flash",
        tools={"dummy_tool": dummy_tool},
        declarations=[],
    )
    harness.run(system_prompt=".", user_message=".")
    assert harness.last_run_cost == pytest.approx(0.01)  # 2 calls × 0.005
