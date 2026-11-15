# -*- coding: utf-8 -*-
"""试几套「多信号组合」规则，比较四组问题的落档；只用开发集，不碰冻结集。"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "experiments"))
logging.disable(logging.CRITICAL)

from rag_engine import load_engine_with_handbook  # noqa: E402
from signal_auc import build_weight, signals  # noqa: E402
from heldout_check import HARD_NEG, HELDOUT_POS  # noqa: E402
from evaluation import EVAL_CASES  # noqa: E402
from negative_probe import NEGATIVE_QUESTIONS  # noqa: E402

COV_LOW = 0.465  # 开发集正例 coverage 的 10% 分位

RULES = {
    "只靠 matched": lambda s: ("low" if s["matched"] < 1 else ("medium" if s["matched"] < 2 else "high")),
    "matched+coverage": lambda s: (
        "low" if s["matched"] < 1 else ("medium" if (s["matched"] < 2 or s["coverage"] < COV_LOW) else "high")
    ),
    "matched+coverage+top1": lambda s: (
        "low"
        if s["matched"] < 1
        else ("medium" if (s["matched"] < 2 or s["coverage"] < COV_LOW or s["top1"] < 0.145) else "high")
    ),
}


def main():
    e = load_engine_with_handbook()
    w = build_weight(e)
    groups = {
        "自带评测题": [c["question"] for c in EVAL_CASES],
        "留出正例": [q for q, _ in HELDOUT_POS],
        "难负例": HARD_NEG,
        "离题负例": NEGATIVE_QUESTIONS,
    }
    feats = {g: [signals(e, w, q)[0] for q in qs] for g, qs in groups.items()}

    for name, rule in RULES.items():
        print(f"\n规则：{name}")
        for g, rows in feats.items():
            c = {"high": 0, "medium": 0, "low": 0}
            for s in rows:
                c[rule(s)] += 1
            print(f"  {g:<8} n={len(rows):<3} 高 {c['high']:<3} 中 {c['medium']:<3} 低 {c['low']:<3}")


if __name__ == "__main__":
    main()
