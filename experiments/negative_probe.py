"""负例探针：拿 20 个「手册里没有」的问题去打检索，看最高分能飙到多少。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe experiments\\negative_probe.py

为什么要这个脚本：
    只凭一个负例（火锅店 0.0879）定阈值是不严谨的——一个样本说明不了分布。
    跑完 20 个负例，你会拿到「负例最高分」，和正例最低分组成一个真实区间，
    这才是阈值该落在的地方。

输出：逐条负例的 top1 分 + 汇总（最高/中位/平均），以及建议区间。
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation import EVAL_CASES  # noqa: E402
from rag_engine import RAGEngine  # noqa: E402

# 20 个明显不在《学生手册》范围内的问句。
# 特意混了几种「看起来像校园、其实手册没写」的，用来测误判。
NEGATIVE_QUESTIONS = [
    "学校火锅店几点关门？",
    "图书馆的 Wi-Fi 密码是什么？",
    "东门那家奶茶店周末营业到几点？",
    "学校附近哪家理发店便宜？",
    "宿舍楼下快递柜怎么取件？",
    "食堂三楼今天有什么菜？",
    "校园卡的支付密码忘了怎么办？",
    "学校停车场的收费标准是多少？",
    "操场跑道一圈多少米？",
    "体育馆的羽毛球场怎么预约？",
    "校医院的牙科几点上班？",
    "宿舍能不能养猫？",
    "学校有几个食堂？",
    "南门几点开门？",
    "校园网一个月多少钱？",
    "自助洗衣机的使用时间是几点到几点？",
    "学校超市卖不卖雨伞？",
    "教室的空调遥控器去哪借？",
    "校园里有没有共享单车？",
    "学校快递站周末开门吗？",
]

CHUNK_SIZE = 280
OVERLAP = 60
TOP_K = 4


def main() -> int:
    engine = RAGEngine(chunk_size=CHUNK_SIZE, overlap=OVERLAP, top_k=TOP_K)
    engine.load_default_handbook()

    print(f"chunk_size={CHUNK_SIZE} overlap={OVERLAP} top_k={TOP_K}  手册块数={len(engine.chunks)}")
    print()
    print(f"{'top1':>7}  {'top2':>7}  问题")
    print("-" * 62)

    top1_scores = []
    for question in NEGATIVE_QUESTIONS:
        hits = engine.retrieve(question, top_k=TOP_K)
        top1 = hits[0][1] if hits else 0.0
        top2 = hits[1][1] if len(hits) > 1 else 0.0
        top1_scores.append(top1)
        flag = "  ← 0.02 会放行" if top1 >= 0.02 else ""
        print(f"{top1:>7.4f}  {top2:>7.4f}  {question}{flag}")

    # 正例最低分（同一套 15 题、同一档参数）
    pos_top1 = []
    for case in EVAL_CASES:
        hits = engine.retrieve(case["question"], top_k=TOP_K)
        if hits:
            pos_top1.append(hits[0][1])

    neg_max = max(top1_scores)
    neg_median = statistics.median(top1_scores)
    pos_min = min(pos_top1)

    print()
    print("汇总：")
    print(f"  负例 top1  最高 {neg_max:.4f} / 中位 {neg_median:.4f} / 平均 {statistics.mean(top1_scores):.4f}")
    print(f"  正例 top1  最低 {pos_min:.4f}（{len(pos_top1)} 题）")
    print(f"  当前门槛 0.02 → 20 个负例里有 {sum(1 for s in top1_scores if s >= 0.02)} 个会被放行")
    print()
    if neg_max < pos_min:
        print(f"  可行阈值区间 = [{neg_max:.4f}, {pos_min:.4f}]")
        print(f"  区间中点 ≈ {(neg_max + pos_min) / 2:.3f}（粗略估计，不是最优解）")
        print("  更稳的做法：按负例分布取高分位，或用 top1 与 top2 的分差判定")
    else:
        print("  负例最高分不低于正例最低分 → 单靠一个阈值分不开，需要换判定方式（例如看分差）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
