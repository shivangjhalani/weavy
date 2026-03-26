"""Unit tests for AgentHarness — mocked Gemini client, no live API calls."""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Mock helpers — minimal objects matching google.genai response shape
# ---------------------------------------------------------------------------

class MockFunctionCall:
    """Mimics google.genai FunctionCall with .name, .args, .id."""

    def __init__(self, name: str, args: dict, call_id: str = "call-001"):
        self.name = name
        self.args = args
        self.id = call_id


class MockPart:
    """Mimics google.genai Part with optional .function_call and .text."""

    def __init__(self, text: str | None = None, function_call: MockFunctionCall | None = None):
        self.text = text
        self.function_call = function_call


class MockContent:
    """Mimics google.genai Content with .parts and .role."""

    def __init__(self, parts: list[MockPart], role: str = "model"):
        self.parts = parts
        self.role = role


class MockCandidate:
    """Mimics a single Candidate with .content."""

    def __init__(self, content: MockContent):
        self.content = content


class MockResponse:
    """Mimics generate_content response with .candidates and .text."""

    def __init__(self, candidates: list[MockCandidate], text: str = ""):
        self.candidates = candidates
        self.text = text


def make_text_response(text: str) -> MockResponse:
    """Helper: response with a single text part, no function calls."""
    part = MockPart(text=text)
    content = MockContent(parts=[part])
    candidate = MockCandidate(content=content)
    return MockResponse(candidates=[candidate], text=text)


def make_fc_response(name: str, args: dict, call_id: str = "call-001") -> MockResponse:
    """Helper: response with a single function_call part."""
    fc = MockFunctionCall(name=name, args=args, call_id=call_id)
    part = MockPart(function_call=fc)
    content = MockContent(parts=[part])
    candidate = MockCandidate(content=content)
    return MockResponse(candidates=[candidate], text="")


def make_mixed_response(text: str, name: str, args: dict, call_id: str = "call-002") -> MockResponse:
    """Helper: response with BOTH a text part AND a function_call part (mixed turn)."""
    text_part = MockPart(text=text)
    fc = MockFunctionCall(name=name, args=args, call_id=call_id)
    fc_part = MockPart(function_call=fc)
    content = MockContent(parts=[text_part, fc_part])
    candidate = MockCandidate(content=content)
    return MockResponse(candidates=[candidate], text=text)


# ---------------------------------------------------------------------------
# MockModels — wraps generate_content with configurable side effects
# ---------------------------------------------------------------------------

class MockModels:
    def __init__(self, responses: list[MockResponse]):
        self._responses = list(responses)
        self._call_count = 0
        self.call_args_list = []

    def generate_content(self, model, contents, config):
        self.call_args_list.append({"model": model, "contents": contents, "config": config})
        resp = self._responses[self._call_count % len(self._responses)]
        self._call_count += 1
        return resp


class MockClient:
    def __init__(self, responses: list[MockResponse]):
        self.models = MockModels(responses)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_harness_instantiation():
    """AgentHarness can be instantiated with model, tools, declarations, client."""
    from lifeos.agent.harness import AgentHarness

    client = MockClient([make_text_response("hello")])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={},
        declarations=[],
        client=client,
    )
    assert harness.model == "gemini-2.5-flash"
    assert not hasattr(harness, "budget")


def test_harness_text_only_response():
    """harness.run returns the text when model replies with no tool calls."""
    from lifeos.agent.harness import AgentHarness

    expected = "The answer is 42."
    client = MockClient([make_text_response(expected)])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={},
        declarations=[],
        client=client,
    )
    result = harness.run(system_prompt="You are helpful.", user_message="What is the answer?")
    assert result == expected


def test_harness_dispatches_tool_call():
    """harness.run dispatches to the registered tool callable when model returns a function call."""
    from lifeos.agent.harness import AgentHarness

    tool_called_with = {}

    def my_tool(x: int, y: int) -> str:
        tool_called_with["x"] = x
        tool_called_with["y"] = y
        return "tool-result"

    # Sequence: first response has FC, second is text
    client = MockClient([
        make_fc_response("my_tool", {"x": 5, "y": 10}, "call-abc"),
        make_text_response("Done!"),
    ])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"my_tool": my_tool},
        declarations=[],
        client=client,
    )
    result = harness.run(system_prompt="Use tools.", user_message="Add numbers.")
    assert result == "Done!"
    assert tool_called_with["x"] == 5
    assert tool_called_with["y"] == 10


def test_harness_tool_receives_correct_kwargs():
    """Tool callable receives the exact kwargs from function_call.args."""
    from lifeos.agent.harness import AgentHarness

    captured = {}

    def capture_tool(**kwargs):
        captured.update(kwargs)
        return "captured"

    client = MockClient([
        make_fc_response("capture_tool", {"alpha": "hello", "beta": 99}, "call-xyz"),
        make_text_response("Done."),
    ])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"capture_tool": capture_tool},
        declarations=[],
        client=client,
    )
    harness.run(system_prompt="Use tools.", user_message="Test kwargs.")
    assert captured == {"alpha": "hello", "beta": 99}


def test_harness_function_response_includes_fc_id():
    """Function response parts include the fc.id from the original call."""
    from lifeos.agent.harness import AgentHarness
    from google.genai import types

    received_contents = []

    class CapturingModels:
        _count = 0
        responses = [
            make_fc_response("my_tool", {"q": "test"}, "call-ID-123"),
            make_text_response("Final answer."),
        ]

        def generate_content(self, model, contents, config):
            received_contents.append(contents)
            resp = self.responses[self._count % len(self.responses)]
            self._count += 1
            return resp

    class CapturingClient:
        models = CapturingModels()

    def my_tool(q: str) -> str:
        return f"result for {q}"

    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"my_tool": my_tool},
        declarations=[],
        client=CapturingClient(),
    )
    harness.run(system_prompt=".", user_message="test")

    # The second call to generate_content receives contents including the function response
    # contents[-1] is the real types.Content the harness built with types.Part(function_response=...)
    second_call_contents = received_contents[1]
    # Walk ALL content items looking for a part with a function_response attribute
    # (skip mock objects that won't have it)
    found_id = None
    for content in second_call_contents:
        if not hasattr(content, "parts"):
            continue
        for p in content.parts:
            if hasattr(p, "function_response") and p.function_response is not None:
                found_id = p.function_response.id
                break
        if found_id is not None:
            break

    assert found_id == "call-ID-123", f"Expected fc.id 'call-ID-123' in function_response, got: {found_id}"


def test_harness_iterates_all_parts():
    """Harness iterates ALL parts in a response, not just parts[0]."""
    from lifeos.agent.harness import AgentHarness

    calls_dispatched = []

    def tool_a(val: str) -> str:
        calls_dispatched.append(("a", val))
        return "a-result"

    def tool_b(val: str) -> str:
        calls_dispatched.append(("b", val))
        return "b-result"

    # Single response with two FC parts (mixed turn)
    fc1 = MockFunctionCall("tool_a", {"val": "first"}, "call-1")
    fc2 = MockFunctionCall("tool_b", {"val": "second"}, "call-2")
    multi_part_content = MockContent(parts=[
        MockPart(function_call=fc1),
        MockPart(function_call=fc2),
    ])
    multi_fc_response = MockResponse(
        candidates=[MockCandidate(multi_part_content)],
        text="",
    )

    client = MockClient([multi_fc_response, make_text_response("all done")])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"tool_a": tool_a, "tool_b": tool_b},
        declarations=[],
        client=client,
    )
    result = harness.run(system_prompt=".", user_message="run both")
    assert result == "all done"
    assert ("a", "first") in calls_dispatched
    assert ("b", "second") in calls_dispatched


def test_harness_runs_until_model_stops():
    """Harness runs tool calls until model returns text-only response (no budget limit)."""
    from lifeos.agent.harness import AgentHarness

    call_count = 0

    def counting_tool(n: int) -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{n}"

    # Model calls tool 5 times before returning text
    responses = [make_fc_response("counting_tool", {"n": i}, f"call-{i}") for i in range(5)]
    responses.append(make_text_response("Done after 5 tool calls."))

    client = MockClient(responses)
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"counting_tool": counting_tool},
        declarations=[],
        client=client,
    )
    result = harness.run(system_prompt=".", user_message="call tools many times")
    assert result == "Done after 5 tool calls."
    assert call_count == 5, f"Expected 5 tool calls, got {call_count}"


def test_harness_returns_string():
    """harness.run always returns a string."""
    from lifeos.agent.harness import AgentHarness

    client = MockClient([make_text_response("response text")])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={},
        declarations=[],
        client=client,
    )
    result = harness.run(system_prompt=".", user_message=".")
    assert isinstance(result, str)
