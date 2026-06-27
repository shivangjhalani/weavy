"""Published LoCoMo reference numbers (gpt-4o-mini backbone).

These are self-reported by vendors/papers on *their own* harnesses and SDK
versions. The public Mem0/Zep dispute showed the same system scoring 58-84 on the
same benchmark depending on methodology, so these are plotted as fuzzy reference
lines for orientation — never as a like-for-like comparison against our harness.

To turn any of these into a true same-harness comparison, add the corresponding
adapter (e.g. ``bench/adapters/mem0_adapter.py``) and run it through this harness.
"""

REFERENCE_LINES: list[dict[str, str]] = [
    {
        "system": "Mem0",
        "metric": "LLM-judge (J), overall",
        "score": "~66.9",
        "source": "Mem0 paper (arXiv:2504.19413)",
    },
    {
        "system": "Mem0g (graph)",
        "metric": "LLM-judge (J), overall",
        "score": "~68.4",
        "source": "Mem0 paper (arXiv:2504.19413)",
    },
    {
        "system": "Zep",
        "metric": "LLM-judge (J), overall",
        "score": "58.4 – 75.1 (disputed)",
        "source": "Zep blog / getzep zep-papers Issue #5",
    },
    {
        "system": "LangMem",
        "metric": "LLM-judge (J), overall",
        "score": "~58",
        "source": "Mem0 paper (arXiv:2504.19413)",
    },
    {
        "system": "OpenAI Memory",
        "metric": "LLM-judge (J), overall",
        "score": "~52",
        "source": "Mem0 paper (arXiv:2504.19413)",
    },
]
