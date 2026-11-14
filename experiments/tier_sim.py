# -*- coding: utf-8 -*-
"""在开发集上模拟三档，比较 matched / coverage 两种信号（规则固定，不搜索）。"""
import logging
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\傻福\Desktop\CampusRAG-Eval\campus-rag")
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "experiments"))
logging.disable(logging.CRITICAL)

from rag_engine import load_engine_with_handbook  # noqa: E402
from signal_auc import build_weight, signals  # noqa: E402
from heldout_check import HARD_NEG, HELDOUT_POS  # noqa: E402
from evaluation import EVAL_CASES  # noqa: E402
from negative_probe import NEGATIVE_QUESTIONS  # noqa: E402


def pct(vals, p):
    v = sorted(vals)
    k = max(0, min(len(v) - 1, int(round((len(v) - 1) * p))))
    return v[k]


def main():
    e = load_engine_with_handbook()
    w = build_weight(e)

    pos_q = [c["question"] for c in EVAL_CASES] + [q for q, _ in HELDOUT_POS]
    pos = [signals(e, w, q)[0] for q in pos_q]
    hard = [signals(e, w, q)[0] for q in HARD_NEG]
    off = [signals(e, w, q)[0] for q in NEGATIVE_QUESTIONS]

    for sig in ("matched", "coverage", "top1", "gap"):
        low = pct([p[sig] for p in pos], 0.10)
        high = max([h[sig] for h in hard] + [o[sig] for o in off])
        def tier(v):
            return "高" if v >= high else ("中" if v >= low else "低")
        pos_c = [tier(p[sig]) for p in pos]
        hard_c = [tier(h[sig]) for h in hard]
        off_c = [tier(o[sig]) for o in off]
        print(f"\n信号 {sig}  low={low:.3f} high={high:.3f}")
        print(f"  正例 {len(pos)}: 高 {pos_c.count('高')} / 中 {pos_c.count('中')} / 低(误拒) {pos_c.count('低')}")
        print(f"  难负例 {len(hard)}: 高(硬答) {hard_c.count('高')} / 中 {hard_c.count('中')} / 低(拒) {hard_c.count('低')}")
        print(f"  离题 {len(off)}: 高(硬答) {off_c.count('高')} / 中 {off_c.count('中')} / 低(拒) {off_c.count('低')}")


if __name__ == "__main__":
    main()
