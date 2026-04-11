"""
Patched LongMemEval evaluate_qa.py — uses litellm instead of the OpenAI SDK
directly, so any litellm-supported model can be used as the judge.

Standalone:
    python eval/evaluate_qa.py gemini/gemini-2.5-flash-lite hyp.jsonl ref.json [out.jsonl]

Programmatic (from eval.py):
    from evaluate_qa import run_judge
    entries = run_judge(hyp_file, ref_file, model, out_file, append=True)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import litellm
import numpy as np
from tqdm import tqdm


# ---------------------------------------------------------------------------
# Judge prompt templates (unchanged from original LongMemEval)
# ---------------------------------------------------------------------------

def get_anscheck_prompt(
    task: str, question: str, answer: str, response: str, abstention: bool = False
) -> str:
    if not abstention:
        if task in ("single-session-user", "single-session-assistant", "multi-session"):
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate "
                "steps to get the correct answer, you should also answer yes. If the response only "
                "contains a subset of the information required by the answer, answer no. \n\n"
                "Question: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == "temporal-reasoning":
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response is equivalent to the correct answer or contains all the intermediate "
                "steps to get the correct answer, you should also answer yes. If the response only "
                "contains a subset of the information required by the answer, answer no. In addition, "
                "do not penalize off-by-one errors for the number of days. If the question asks for "
                "the number of days/weeks/months, etc., and the model makes off-by-one errors "
                "(e.g., predicting 19 days when the answer is 18), the model's response is still "
                "correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == "knowledge-update":
            template = (
                "I will give you a question, a correct answer, and a response from a model. "
                "Please answer yes if the response contains the correct answer. Otherwise, answer no. "
                "If the response contains some previous information along with an updated answer, "
                "the response should be considered as correct as long as the updated answer is the "
                "required answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\n"
                "Is the model response correct? Answer yes or no only."
            )
        elif task == "single-session-preference":
            template = (
                "I will give you a question, a rubric for desired personalized response, and a "
                "response from a model. Please answer yes if the response satisfies the desired "
                "response. Otherwise, answer no. The model does not need to reflect all the points "
                "in the rubric. The response is correct as long as it recalls and utilizes the "
                "user's personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\n"
                "Model Response: {}\n\nIs the model response correct? Answer yes or no only."
            )
        else:
            raise NotImplementedError(f"Unknown task type: {task!r}")
    else:
        template = (
            "I will give you an unanswerable question, an explanation, and a response from a model. "
            "Please answer yes if the model correctly identifies the question as unanswerable. "
            "The model could say that the information is incomplete, or some other information is "
            "given but the asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\n"
            "Model Response: {}\n\nDoes the model correctly identify the question as unanswerable? "
            "Answer yes or no only."
        )
    return template.format(question, answer, response)


# ---------------------------------------------------------------------------
# LiteLLM judge call (replaces openai.chat.completions.create)
# ---------------------------------------------------------------------------

def _judge_call(model: str, prompt: str) -> str:
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=10,
        num_retries=5,
    )
    return response.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Core judge function
# ---------------------------------------------------------------------------

def run_judge(
    hyp_file: Path | str,
    ref_file: Path | str,
    model: str,
    out_file: Path | str | None = None,
    *,
    append: bool = False,
    verbose: bool = True,
) -> list[dict]:
    """Judge hypotheses against reference answers using the given litellm model.

    Args:
        hyp_file:  JSONL file with {question_id, hypothesis, ...} per line.
        ref_file:  LongMemEval reference JSON (list of instances).
        model:     litellm model string, e.g. "gemini/gemini-2.5-flash-lite".
        out_file:  Where to write judged results. Defaults to hyp_file + ".eval-{model_slug}".
        append:    If True, append to out_file rather than overwriting.
        verbose:   Print each judgement while running.

    Returns:
        List of judged entries (each has autoeval_label added).
    """
    hyp_file = Path(hyp_file)
    ref_file = Path(ref_file)

    hyp_lines = hyp_file.read_text().splitlines()
    hypotheses = [json.loads(line) for line in hyp_lines if line.strip()]

    with open(ref_file) as f:
        references = json.load(f)
    qid2qdata = {e["question_id"]: e for e in references}
    qid2qtype = {e["question_id"]: e["question_type"] for e in references}

    if out_file is None:
        model_slug = model.replace("/", "-").replace(":", "-")
        out_file = hyp_file.parent / f"{hyp_file.stem}.eval-{model_slug}.jsonl"
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    judged: list[dict] = []

    with open(out_file, mode) as f:
        for entry in tqdm(hypotheses, desc="judging"):
            qid = entry["question_id"]
            if qid not in qid2qtype:
                print(f"[warn] {qid} not in reference data, skipping")
                continue

            qtype = qid2qtype[qid]
            question = qid2qdata[qid]["question"]
            answer = qid2qdata[qid]["answer"]
            hypothesis = entry["hypothesis"]
            abstention = "_abs" in qid

            prompt = get_anscheck_prompt(qtype, question, answer, hypothesis, abstention)
            raw = _judge_call(model, prompt)
            label = "yes" in raw.lower()

            entry = dict(entry)
            entry["autoeval_label"] = {"model": model, "label": label}
            judged.append(entry)

            if verbose:
                print(json.dumps({
                    "question": question,
                    "answer": answer,
                    "hypothesis": hypothesis,
                    "label": label,
                }, ensure_ascii=False), flush=True)

            f.write(json.dumps(entry) + "\n")

    qtypes = {e["question_type"] for e in references}
    qtype2acc: dict[str, list[int]] = {t: [] for t in qtypes}
    for e in judged:
        qtype2acc[qid2qtype[e["question_id"]]].append(1 if e["autoeval_label"]["label"] else 0)

    overall = [1 if e["autoeval_label"]["label"] else 0 for e in judged]
    print(f"\nAccuracy: {np.mean(overall):.4f}" if overall else "")
    for k, v in qtype2acc.items():
        if v:
            print(f"  {k}: {np.mean(v):.4f} ({len(v)})")

    print(f"Saved to {out_file}")
    return judged


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print("Usage: python evaluate_qa.py <model> <hyp_file> <ref_file> [out_file]")
        print("  model    — litellm model string, e.g. gemini/gemini-2.5-flash-lite")
        print("  hyp_file — JSONL hypotheses (question_id + hypothesis per line)")
        print("  ref_file — LongMemEval reference JSON")
        print("  out_file — optional output path (default: hyp_file.eval-<model>.jsonl)")
        sys.exit(1)

    run_judge(
        hyp_file=sys.argv[2],
        ref_file=sys.argv[3],
        model=sys.argv[1],
        out_file=sys.argv[4] if len(sys.argv) == 5 else None,
    )
