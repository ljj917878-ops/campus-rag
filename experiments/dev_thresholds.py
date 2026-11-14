"""在开发集上按事先说好的规则定三档阈值（不看冻结集）。

规则（写死，不搜索）：
  1. 信号 = 开发集上「对难负例 AUC 最高」的那个（2026-11-14 实测是 matched）。
  2. low  = 开发集里「检索正确」的正例信号值的 10% 分位数。
  3. high = 开发集所有负例（离题 + 难负例）信号值的最大值。

开发集 = 训练正例 15（evaluation.EVAL_CASES）+ 留出正例 12（heldout_check.HELDOUT_POS）
        + 负例 34（threshold_scan）+ 难负例 11（HARD_NEG）+ 离题 20（negative_probe）
"""

import logging
import statistics
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\傻福\Desktop\CampusRAG-Eval\campus-rag")
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "experiments"))
logging.disable(logging.CRITICAL)

from signal_auc import SIGNALS, build_weight, signals  # noqa: E402
from rag_engine import load_engine_with_handbook  # noqa: E402

from heldout_check import HARD_NEG, HELDOUT_POS  # noqa: E402
from negative_probe import NEGATIVE_QUESTIONS  # noqa: E402
from evaluation import EVAL_CASES  # noqa: E402

try:
    from threshold_scan import NEGATIVES as SCAN_NEG  # noqa: E402
except Exception:
    SCAN_NEG = []


def pct(vals, p):
    vals = sorted(vals)
    if not vals:
        return float("nan")
    k = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * p))))
    return vals[k]


def main() -> None:
    engine = load_engine_with_handbook()
    weight = build_weight(engine)

    train_q = [c["question"] for c in EVAL_CASES]
    held_q = [q for q, _ in HELDOUT_POS]
    neg_q = list(SCAN_NEG) + list(HARD_NEG) + list(NEGATIVE_QUESTIONS)

    def collect(qs):
        out = []
        for q in qs:
            sig, c1 = signals(engine, weight, q)
            out.append(sig)
        return out

    train = collect(train_q)
    held = collect(held_q)
    negs = collect(neg_q)

    print(f"开发集：训练正例 {len(train)} / 留出正例 {len(held)} / 负例 {len(negs)}\n")
    print(f"{'信号':<10}{'训练中位':>10}{'留出10%':>10}{'负例最大':>10}{'负例95%':>10}")
    for s in SIGNALS:
        tr = [r[s] for r in train]
        he = [r[s] for r in held]
        ng = [r[s] for r in negs]
        print(f"{s:<10}{statistics.median(tr):>10.3f}{pct(he, 0.10):>10.3f}"
              f"{max(ng):>10.3f}{pct(ng, 0.95):>10.3f}")

    print("\n按事先规则取：信号 matched（开发集上对难负例 AUC 最高）")
    he = sorted(r["matched"] for r in held)
    ng = sorted(r["matched"] for r in negs)
    print(f"  留出正例 matched 分布：{he}")
    print(f"  负例 matched 分布（前 10 高）：{ng[-10:]}")
    print(f"  low = 留出正例 10% 分位 = {pct(he, 0.10)}")
    print(f"  high = 负例最大 = {max(ng)}")


if __name__ == "__main__":
    main()
