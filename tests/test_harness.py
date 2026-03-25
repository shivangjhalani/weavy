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
    """AgentHarness can be instantiated with model, tools, declarations, budget."""
    from lifeos.agent.harness import AgentHarness

    client = MockClient([make_text_response("hello")])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={},
        declarations=[],
        budget=3,
        client=client,
    )
    assert harness.model == "gemini-2.5-flash"
    assert harness.budget == 3


def test_harness_text_only_response():
    """harness.run returns the text when model replies with no tool calls."""
    from lifeos.agent.harness import AgentHarness

    expected = "The answer is 42."
    client = MockClient([make_text_response(expected)])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={},
        declarations=[],
        budget=3,
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
        budget=5,
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
        budget=3,
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
        budget=3,
        client=CapturingClient(),
    )
    harness.run(system_prompt=".", user_message="test")

    # The second call to generate_content should have the function response in contents
    # contents[-1] should be a Content with parts that include function_response with id
    second_call_contents = received_contents[1]
    function_response_content = second_call_contents[-1]
    # It's a real types.Content — check the part has a function_response with the right id
    fr_part = function_response_content.parts[0]
    assert fr_part.function_response.id == "call-ID-123"


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
        budget=5,
        client=client,
    )
    result = harness.run(system_prompt=".", user_message="run both")
    assert result == "all done"
    assert ("a", "first") in calls_dispatched
    assert ("b", "second") in calls_dispatched


def test_harness_budget_enforcement():
    """When budget=2 and model keeps returning tool calls, harness stops after 2 and forces final answer."""
    from lifeos.agent.harness import AgentHarness

    call_count = 0

    def counting_tool(n: int) -> str:
        nonlocal call_count
        call_count += 1
        return f"result-{n}"

    # Always return a function call — budget should stop this
    always_fc = make_fc_response("counting_tool", {"n": 1}, "call-loop")
    # Final answer after budget exhausted
    final_answer = make_text_response("I have exhausted my budget, here is my answer.")

    class BudgetTestModels:
        _count = 0

        def generate_content(self, model, contents, config):
            result = always_fc if self._count < 4 else final_answer
            self._count += 1
            return result

    class BudgetTestClient:
        models = BudgetTestModels()

    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"counting_tool": counting_tool},
        declarations=[],
        budget=2,
        client=BudgetTestClient(),
    )
    result = harness.run(system_prompt=".", user_message="loop forever")

    # Tool should have been called at most `budget` times
    assert call_count <= 2, f"Tool was called {call_count} times, expected <= 2"
    # Result must be a string (forced final answer)
    assert isinstance(result, str)


def test_harness_budget_injects_exhausted_message():
    """When budget is exhausted, harness injects the budget-exhausted turn before forcing final answer."""
    from lifeos.agent.harness import AgentHarness

    injected_contents = []

    class TrackingModels:
        _count = 0
        always_fc = make_fc_response("t", {}, "c1")
        final = make_text_response("final")

        def generate_content(self, model, contents, config):
            # Record what contents were passed on the budget-exhausted call
            if self._count == 1:  # second call = after budget hit
                injected_contents.extend(contents)
            resp = self.always_fc if self._count < 3 else self.final
            self._count += 1
            return resp

    class TrackingClient:
        models = TrackingModels()

    def t() -> str:
        return "ok"

    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"t": t},
        declarations=[],
        budget=1,
        client=TrackingClient(),
    )
    harness.run(system_prompt=".", user_message="test")

    # Find if any content includes the budget-exhausted text
    all_text = []
    for c in injected_contents:
        if hasattr(c, "parts"):
            for p in c.parts:
                if hasattr(p, "text") and p.text:
                    all_text.append(p.text)

    budget_msg_found = any("budget exhausted" in t.lower() for t in all_text)
    assert budget_msg_found, f"Budget exhaustion message not found in injected contents. Texts: {all_text}"


def test_harness_returns_string():
    """harness.run always returns a string."""
    from lifeos.agent.harness import AgentHarness

    client = MockClient([make_text_response("response text")])
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={},
        declarations=[],
        budget=3,
        client=client,
    )
    result = harness.run(system_prompt=".", user_message=".")
    assert isinstance(result, str)
