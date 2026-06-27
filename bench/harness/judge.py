"""LLM-as-judge scoring — the LoCoMo "J" metric.

A small, deterministic grader decides whether a predicted answer matches the gold
answer. Recall questions and adversarial questions use different rubrics:

- Recall (categories 1-4): correct if the prediction conveys the gold fact, even
  if phrased differently or with extra correct detail.
- Adversarial (category 5): the question carries a false premise; correct means
  the system refused / corrected / abstained rather than confirming the trap.

The judge is called through LiteLLM so it shares the project's provider config.
It returns a structured, parseable verdict and never raises on a bad answer — a
malformed judge reply is recorded as ``error`` and counted incorrect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import litellm

from bench.adapters.base import Usage

_RECALL_SYSTEM = """You grade a memory system's answer against a gold answer.

Judge ONE thing: does the prediction CONTAIN (or clearly entail) the key fact in \
the gold answer? If yes, it is CORRECT — even if it is long-winded, adds extra \
correct detail, lists additional items, or phrases things differently. Verbosity \
and extra information NEVER make an answer incorrect.

Mark INCORRECT only if the prediction: contradicts the gold answer, gives a wrong \
entity/number/date, omits the gold fact entirely, or says it does not know when \
the gold fact exists.

Examples:
- gold "Psychology, counseling certification"; prediction "Counseling and \
psychology, plus social work" -> CORRECT (contains the gold fact).
- gold "Transgender woman"; prediction a paragraph about advocacy that never says \
she is transgender -> INCORRECT (omits the gold fact).

Respond with ONLY a JSON object: {"correct": true|false, "reason": "<short>"}."""

_ADVERSARIAL_SYSTEM = """You grade a memory system on an ADVERSARIAL question that \
contains a false or unanswerable premise. The system SHOULD refuse, correct the \
premise, or say the information is not available. Mark CORRECT if it does any of \
those. Mark INCORRECT if it confirms the false premise or fabricates a specific \
answer. The expected (correct) response is given as the gold answer.
Respond with ONLY a JSON object: {"correct": true|false, "reason": "<short>"}."""


@dataclass
class Verdict:
    correct: bool
    reason: str
    usage: Usage
    error: str | None = None


def _usage_of(response) -> Usage:
    u = getattr(response, "usage", None)
    if not u:
        return Usage()
    return Usage(
        prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(u, "completion_tokens", 0) or 0,
        total_tokens=getattr(u, "total_tokens", 0) or 0,
    )


def _parse(content: str) -> tuple[bool, str]:
    """Extract the verdict JSON, tolerating code fences / surrounding prose."""
    text = content.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)
    return bool(data["correct"]), str(data.get("reason", ""))


def judge_answer(
    *,
    question: str,
    gold: str,
    prediction: str,
    is_adversarial: bool,
    model: str,
) -> Verdict:
    """Return a :class:`Verdict` for one (question, gold, prediction)."""
    if not prediction.strip():
        # Empty prediction: a miss for recall, a (weak) pass for adversarial only
        # if the system genuinely produced nothing to assert.
        if not is_adversarial:
            return Verdict(False, "Empty prediction.", Usage())

    system = _ADVERSARIAL_SYSTEM if is_adversarial else _RECALL_SYSTEM
    user = (
        f"Question: {question}\n"
        f"Gold answer: {gold}\n"
        f"Predicted answer: {prediction or '(no answer given)'}"
    )
    try:
        response = litellm.completion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        correct, reason = _parse(content)
        return Verdict(correct, reason, _usage_of(response))
    except Exception as e:  # malformed reply or call failure -> incorrect, logged
        return Verdict(False, "", Usage(), error=str(e))
