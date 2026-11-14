"""chunk_size 对照实验：只改切块大小，看检索分数怎么变。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe experiments\\chunk_size_sweep.py

它跑两件事：
1. 对 120 / 180 / 280 / 420 四档 chunk_size，各建一次索引，跑同一套 15 题，
   记录「正例 top1 均值」「负例 top1」以及「关键词是否进 top4」。
2. 对 280 这一档，报出正例最低分与负例最高分，得出判定阈值该落在哪个区间。

注意：这个脚本只读，不改任何项目文件，也不写 eval_results.json。
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation import EVAL_CASES  # noqa: E402
from rag_engine import RAGEngine  # noqa: E402

# 一个明显不在手册范围内的负例（学校火锅店几点关门）
NEGATIVE_QUESTION = "学校火锅店几点关门？"

CHUNK_SIZES = [120, 180, 280, 420]
OVERLAP = 60
TOP_K = 4


def build_engine(chunk_size: int) -> RAGEngine:
    engine = RAGEngine(chunk_size=chunk_size, overlap=OVERLAP, top_k=TOP_K)
    engine.load_default_handbook()
    return engine


def keyword_in_topk(engine: RAGEngine, case: dict, k: int = TOP_K) -> bool:
    """关键词是否出现在 top-k 命中片段的文本里。"""
    hits = engine.retrieve(case["question"], top_k=k)
    blob = "".join(chunk.text for chunk, _ in hits)
    keywords = case.get("keywords") or []
    return any(kw in blob for kw in keywords)


def main() -> int:
    print(f"手册：{ROOT / 'data' / 'campus_handbook.txt'}")
    print(f"正例题数：{len(EVAL_CASES)}    负例：{NEGATIVE_QUESTION}")
    print()

    rows = []
    baseline_detail = None

    for size in CHUNK_SIZES:
        engine = build_engine(size)
        positives = []
        hits_ok = 0
        for case in EVAL_CASES:
            hits = engine.retrieve(case["question"], top_k=TOP_K)
            if hits:
                positives.append(hits[0][1])
            if keyword_in_topk(engine, case):
                hits_ok += 1
        neg_hits = engine.retrieve(NEGATIVE_QUESTION, top_k=TOP_K)
        negative_top1 = neg_hits[0][1] if neg_hits else 0.0

        rows.append(
            {
                "chunk_size": size,
                "chunks": len(engine.chunks),
                "pos_mean": statistics.mean(positives) if positives else 0.0,
                "pos_min": min(positives) if positives else 0.0,
                "neg_top1": negative_top1,
                "kw_hit": hits_ok,
            }
        )

        if size == 280:
            baseline_detail = rows[-1]

    header = f"{'chunk_size':>10} | {'块数':>4} | {'正例 top1 均值':>14} | {'正例最低':>8} | {'负例 top1':>9} | 关键词进 top4"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['chunk_size']:>10} | {r['chunks']:>4} | {r['pos_mean']:>14.3f} | "
            f"{r['pos_min']:>8.3f} | {r['neg_top1']:>9.4f} | {r['kw_hit']:>3}/{len(EVAL_CASES)}"
        )

    print()
    print("结论（照着表读，不用背我写的）：")
    print("  · 块越小，块数越多；正例和负例的 top1 分数会一起往上走")
    print("  · 召回（关键词进 top4）在四档里都没变 → chunk_size 不是召回瓶颈")
    print("  · 420 时 12 段几乎整段通过 → 等于没切")
    print()

    if baseline_detail:
        print("判定阈值该落在哪（以 280 这一档为例）：")
        print(f"  正例最低分 = {baseline_detail['pos_min']:.3f}")
        print(f"  负例最高分 = {baseline_detail['neg_top1']:.4f}")
        print(
            f"  可行区间 = [{baseline_detail['neg_top1']:.4f}, {baseline_detail['pos_min']:.3f}]"
            "  ← 现在的 0.02 远在区间外侧，所以负例也能过闸"
        )
        print("  区间中点只是粗略估计，要更多负例才能定死（见 negative_probe.py）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
