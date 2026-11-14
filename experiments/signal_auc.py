"""信号体检：不做判定方案，先给每个候选信号算 AUC。

背景（2026-11-14）：
    留出测试把「分差 ≥ 0.13」这条规则打翻了——正例 12 条只放行 6 条。
    说明我们先前是「先选方案，再找证据」。这个脚本反过来：
    把可能的信号各自摊开，在留出集上算 AUC，先看谁真的有分辨力。

信号：
    top1        最高相似度
    gap         top1 − top2（相邻块有 60 字重叠时会变小）
    idf_cov     查询词按 IDF 加权的覆盖率 = 命中词 IDF 和 / 查询词 IDF 和
    hit_ratio   命中实词数 / 查询实词数（不按 IDF 加权）
    hit_count   命中的不同实词个数（绝对值，对短问句不公平，仅作对照）

分组（不混在一起报）：
    pos          12 条换了问法的正例
    neg_in       11 条「话题在手册里、这件事没写」的难负例
    neg_off      20 条明显离题的负例

用法（仓库根目录）：
    .venv\\Scripts\\python.exe experiments\\signal_auc.py
    .venv\\Scripts\\python.exe experiments\\signal_auc.py --boot 2000
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.disable(logging.CRITICAL)

from rag_engine import _jieba_analyzer, load_engine_with_handbook  # noqa: E402

from heldout_check import HARD_NEG, HELDOUT_POS  # noqa: E402
from negative_probe import NEGATIVE_QUESTIONS  # noqa: E402

SIGNALS = ["top1", "gap", "idf_cov", "hit_ratio", "hit_count"]


def query_terms(question: str) -> list[str]:
    """和索引同一套分词，去掉空白与单字标点。"""
    return [t for t in _jieba_analyzer(question) if t.strip()]


def features(engine, question: str) -> dict[str, float]:
    hits = engine.retrieve(question, top_k=2)
    c1, s1 = hits[0]
    s2 = hits[1][1] if len(hits) > 1 else 0.0

    vec = engine._vectorizer
    vocab = vec.vocabulary_
    idf = vec.idf_

    terms = query_terms(question)
    chunk_terms = set(_jieba_analyzer(c1.text))
    total_idf = 0.0
    hit_idf = 0.0
    hits_n = 0
    for t in terms:
        idx = vocab.get(t)
        w = float(idf[idx]) if idx is not None else float(idf.max())
        total_idf += w
        if t in chunk_terms:
            hit_idf += w
            hits_n += 1

    n = max(1, len(terms))
    return {
        "top1": float(s1),
        "gap": float(s1 - s2),
        "idf_cov": (hit_idf / total_idf) if total_idf > 0 else 0.0,
        "hit_ratio": hits_n / n,
        "hit_count": float(hits_n),
    }


def auc(pos: list[float], neg: list[float]) -> float:
    """Mann–Whitney U 形式的 AUC；并列按 0.5 计。"""
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def bootstrap_ci(pos, neg, rounds: int, rng: random.Random) -> tuple[float, float]:
    vals = []
    for _ in range(rounds):
        p = [rng.choice(pos) for _ in pos]
        n = [rng.choice(neg) for _ in neg]
        vals.append(auc(p, n))
    vals.sort()
    lo = vals[int(0.025 * len(vals))]
    hi = vals[int(0.975 * len(vals)) - 1]
    return lo, hi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=1000, help="bootstrap 次数")
    ap.add_argument("--seed", type=int, default=20261114)
    args = ap.parse_args()

    engine = load_engine_with_handbook()

    pos_q = [q for q, _ in HELDOUT_POS]
    pos = [features(engine, q) for q in pos_q]
    neg_in = [features(engine, q) for q in HARD_NEG]
    neg_off = [features(engine, q) for q in NEGATIVE_QUESTIONS]

    print(f"样本：正例 {len(pos)} / 话题内缺失负例 {len(neg_in)} / 离题负例 {len(neg_off)}")
    print("AUC = 随机取一个正例和一个负例，正例分数更高的概率。0.5 等于瞎猜。\n")

    rng = random.Random(args.seed)
    rows = []
    for sig in SIGNALS:
        p = [r[sig] for r in pos]
        for group_name, group in (("neg_in", neg_in), ("neg_off", neg_off)):
            n = [r[sig] for r in group]
            a = auc(p, n)
            lo, hi = bootstrap_ci(p, n, args.boot, rng)
            rows.append((group_name, sig, a, lo, hi))

    for group_name, title in (("neg_in", "对照：话题内缺失（难负例）"), ("neg_off", "对照：离题负例")):
        print(f"【{title}】")
        print(f"  {'信号':<10}{'AUC':>7}   {'95% CI':<16}判断")
        for g, sig, a, lo, hi in rows:
            if g != group_name:
                continue
            if a >= 0.9:
                verdict = "很强"
            elif a >= 0.8:
                verdict = "可用"
            elif a >= 0.65:
                verdict = "弱"
            else:
                verdict = "≈瞎猜，丢掉"
            print(f"  {sig:<10}{a:>7.3f}   [{lo:.2f}, {hi:.2f}]{'':<4}{verdict}")
        print()

    print("读法：")
    print("  · CI 很宽 = 样本太小，别在这个集合上定阈值，只能用来排序信号。")
    print("  · 话题内缺失的难负例，词面信号本来就分不开（同义词与真缺失长得一样）。")
    print("  · 下一个脚本要做的：只保留 AUC 明显 > 0.5 的信号，做三档输出，阈值用交叉验证选。")


if __name__ == "__main__":
    main()
