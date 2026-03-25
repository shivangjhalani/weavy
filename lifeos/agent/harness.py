"""AgentHarness — manual dispatch loop with tool-call budget enforcement.

Per D-06: Roll our own loop for control and instrumentation.
Per D-07: Tools as dict mapping names to callables.
Per D-08: Budget enforced by counter; force final answer on exhaustion.

Usage:
    harness = AgentHarness(
        model="gemini-2.5-flash",
        tools={"my_tool": my_callable},
        declarations=[my_fn_declaration],
        budget=8,
    )
    result = harness.run(system_prompt=prompt_text, user_message="User query here.")
"""
from typing import Any, Callable

from google import genai
from google.genai import types


class AgentHarness:
    """Manual dispatch loop with tool-call budget enforcement.

    All three agent roles (ingest, query, memo) use this same harness
    with different system prompts and tool sets.
    """

    def __init__(
        self,
        model: str,
        tools: dict[str, Callable[..., Any]],
        declarations: list,
        budget: int = 8,
        client: genai.Client | None = None,
    ):
        """
        Args:
            model: Gemini model name, e.g. "gemini-2.5-flash".
            tools: Dict mapping tool name to Python callable.
            declarations: List of FunctionDeclaration objects for the Gemini API.
            budget: Maximum number of tool calls before forcing a final answer.
            client: Optional pre-built genai.Client (for testing with mocks).
        """
        self.model = model
        self.tools = tools
        self.declarations = declarations
        self.budget = budget
        self.client = client or genai.Client()

    def run(self, system_prompt: str, user_message: str) -> str:
        """Run the agent loop and return the final text response.

        Args:
            system_prompt: Role-specific system instruction (loaded from prompts/*.md).
            user_message: The user's input (transcript, question, etc.).

        Returns:
            Final text response from the model as a string.
        """
        tool_config = types.Tool(function_declarations=self.declarations)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tool_config],
        )
        contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]
        calls_used = 0

        while True:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            # Append model response to conversation history
            contents.append(response.candidates[0].content)

            # Check ALL parts for function calls (not just parts[0] — Pitfall 4)
            fc_parts = [p for p in response.candidates[0].content.parts if p.function_call]

            if not fc_parts:
                # Model returned no tool calls — it is done
                return response.text

            if calls_used >= self.budget:
                # Budget exhausted — inject message and force a final answer (D-08)
                # "Force final answer" is preferred over hard cutoff: guarantees a usable
                # response even when tool calls ran dry mid-reasoning.
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=(
                                    "Tool call budget exhausted. You must now provide your final answer "
                                    "based only on what you have retrieved so far. Do not request more tools."
                                )
                            )
                        ],
                    )
                )
                final = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(system_instruction=system_prompt),
                )
                return final.text

            # Dispatch all function calls in this turn and collect responses
            response_parts = []
            for part in fc_parts:
                fc = part.function_call
                result = self.tools[fc.name](**fc.args)
                calls_used += 1
                # REQUIRED — Pitfall 3: fc.id must be echoed in FunctionResponse for SDK mapping.
                # types.Part.from_function_response() does not accept `id` in this SDK version;
                # use types.Part(function_response=types.FunctionResponse(...)) directly.
                response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result},
                            id=fc.id,
                        )
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
