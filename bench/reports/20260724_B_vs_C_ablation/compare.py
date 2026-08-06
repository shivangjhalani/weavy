"""Paired comparison of base / bnav / cfall answer runs.

Reads the three results.jsonl files and reports, per condition:
- overall + per-category recall (non-adversarial), adversarial abstention
- answer tokens/question
And paired vs base:
- questions base got WRONG that the condition got RIGHT (recovered)
- questions base got RIGHT that the condition got WRONG (regressed)
"""

import json
import sys
from collections import Counter, defaultdict

RUNS = sys.argv[1:] or ["run_base", "run_bnav", "run_cfall"]
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load(run):
    rows, buf = [], ""
    for line in open(f"{BASE_DIR}/{run}/results.jsonl"):
        buf += line
        try:
            rows.append(json.loads(buf)); buf = ""
        except json.JSONDecodeError:
            pass
    return {r["question"] + "|" + str(r["gold"]): r for r in rows}


def truth(r):
    return str(r["correct"]) == "True"


def adv(r):
    return str(r["is_adversarial"]) == "True"


data = {run: load(run) for run in RUNS}
base = data[RUNS[0]]

print(f"{'condition':12s} {'overall':>8s} {'single':>8s} {'multi':>8s} "
      f"{'temporal':>9s} {'open':>6s} {'adv':>6s} {'tok/q':>8s}")
for run in RUNS:
    d = data[run]
    na = [r for r in d.values() if not adv(r)]
    cats = defaultdict(list)
    for r in na:
        cats[r["category_name"]].append(truth(r))
    overall = sum(truth(r) for r in na) / len(na)
    advs = [r for r in d.values() if adv(r)]
    adv_acc = sum(truth(r) for r in advs) / len(advs) if advs else float("nan")
    tok = sum(int(r["answer_total_tokens"]) for r in d.values()) / len(d)

    def cat(name):
        v = cats.get(name, [])
        return sum(v) / len(v) if v else float("nan")

    print(f"{run:12s} {overall:>7.1%} {cat('single_hop'):>7.1%} "
          f"{cat('multi_hop'):>7.1%} {cat('temporal'):>8.1%} "
          f"{cat('open_domain'):>5.1%} {adv_acc:>5.1%} {tok:>8.0f}")

print()
for run in RUNS[1:]:
    d = data[run]
    recovered, regressed = [], []
    for k, br in base.items():
        if k not in d or adv(br):
            continue
        cr = d[k]
        if not truth(br) and truth(cr):
            recovered.append(cr)
        elif truth(br) and not truth(cr):
            regressed.append(cr)
    print(f"=== {run} vs {RUNS[0]} ===")
    print(f"  recovered (base wrong -> right): {len(recovered)}  "
          f"by cat {dict(Counter(r['category_name'] for r in recovered))}")
    print(f"  regressed (base right -> wrong): {len(regressed)}  "
          f"by cat {dict(Counter(r['category_name'] for r in regressed))}")
    print(f"  net: {len(recovered) - len(regressed):+d}")
    for r in recovered[:8]:
        print(f"    +[{r['category_name']}] {r['question'][:60]} | gold: {str(r['gold'])[:40]}")
    print()
