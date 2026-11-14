# -*- coding: utf-8 -*-
"""三档判定上线后的对照：同一批问题，看 high / medium / low 怎么落，以及硬答有没有降下来。"""
import logging
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\傻福\Desktop\CampusRAG-Eval\campus-rag")
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "experiments"))
logging.disable(logging.CRITICAL)

from rag_engine import load_engine_with_handbook  # noqa: E402
from heldout_check import HARD_NEG, HELDOUT_POS  # noqa: E402
from evaluation import EVAL_CASES  # noqa: E402
from negative_probe import NEGATIVE_QUESTIONS  # noqa: E402

e = load_engine_with_handbook()


def run(label, questions):
    tiers = {"high": 0, "medium": 0, "low": 0}
    for q in questions:
        r = e.ask(q)
        tiers[r.tier] = tiers.get(r.tier, 0) + 1
    n = len(questions)
    print(f"{label:<10} n={n:<3} 高 {tiers['high']:<3} 中 {tiers['medium']:<3} 低 {tiers['low']:<3}")


run("自带评测题", [c["question"] for c in EVAL_CASES])
run("留出正例", [q for q, _ in HELDOUT_POS])
run("难负例", HARD_NEG)
run("离题负例", NEGATIVE_QUESTIONS)
