"""阈值扫描：把「绝对分数能不能当门槛」这件事算清楚。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe experiments\\threshold_scan.py

它做四件事：
1. 正例：evaluation.py 里的 15 题，记 top1 与「top1 − top2」。
2. 负例：脚本里的 35 条（本仓库 20 条 + 外部评审给的 15 条，去重）手册外问题，
   同样记 top1 与分差。这些负例已逐条核对：手册里确实没有对应条款。
3. 阈值从 0.01 扫到 0.30，看「正例通过率」「负例拒答率」「均衡准确率」怎么变。
4. 单独看「分差」能不能把正负例分开——这是本脚本最重要的结论。

为什么要两套负例合并：换一批负例，绝对分数的最高值就从 0.171 变成 0.2014，
结论会翻转；而分差在两套里都稳定。这个差别本身就是结论。
"""

from __future__ import annotations

import logging
import statistics
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation import EVAL_CASES  # noqa: E402
from rag_engine import load_engine_with_handbook  # noqa: E402

# A 组：本仓库自带的 20 条（偏「校园生活细节」，最容易误判）
NEGATIVES_A = [
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

# B 组：外部评审给的 15 条（偏「办事流程」，与校园相关但手册没写）
NEGATIVES_B = [
    "学校火锅店几点关门？",
    "附近地铁几号线到学校？",
    "今天天气怎么样？",
    "怎么办理港澳通行证？",
    "食堂牛肉面多少钱一碗？",
    "图书馆的无线网络密码是多少？",
    "校长的办公电话是多少？",
    "学校篮球联赛什么时候开赛？",
    "怎么考机动车驾驶证？",
    "校车几点从东门发车？",
    "怎么申请出国留学签证？",
    "校园里能不能骑共享单车？",
    "学校附近有没有好吃的奶茶店？",
    "怎么把户口迁到学校？",
    "学校的微信公众号叫什么？",
]


def dedupe(items: list[str]) -> list[str]:
    """按归一化文本去重，保留首次出现。"""
    seen, out = set(), []
    for q in items:
        key = q.replace(" ", "").replace("?", "").replace("？", "")
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def probe(engine, question: str) -> tuple[float, float]:
    hits = engine.retrieve(question, top_k=2)
    scores = [score for _chunk, score in hits]
    top1 = scores[0] if scores else 0.0
    top2 = scores[1] if len(scores) > 1 else 0.0
    return top1, top1 - top2


def describe(name: str, values: list[float]) -> None:
    print(f"  {name}: 最小 {min(values):.4f} / 中位 {statistics.median(values):.4f} / 最大 {max(values):.4f}")


def sweep(pos: list[tuple[float, float]], neg: list[tuple[float, float]]) -> None:
    print(f"\n{'阈值':>6} {'正例通过率':>10} {'负例拒答率':>10} {'均衡准确率':>10}")
    print("-" * 44)
    best_th, best_bal = None, -1.0
    for i in range(1, 31):
        th = i / 100
        keep = sum(s >= th for s, _ in pos) / len(pos)
        reject = sum(s < th for s, _ in neg) / len(neg)
        bal = (keep + reject) / 2
        mark = ""
        if bal > best_bal:
            best_th, best_bal, mark = th, bal, "  ←"
        print(f"{th:>6.2f} {keep:>9.0%} {reject:>10.0%} {bal:>10.2f}{mark}")
    print(f"\n绝对分数的最优阈值：{best_th:.2f}（均衡准确率 {best_bal:.2f}）")


def main() -> int:
    engine = load_engine_with_handbook()
    negatives = dedupe(NEGATIVES_A + NEGATIVES_B)

    pos = [probe(engine, c["question"]) for c in EVAL_CASES]
    neg = [probe(engine, q) for q in negatives]

    print(f"正例 {len(pos)} 条 · 负例 {len(neg)} 条（A 组 {len(NEGATIVES_A)} + B 组 {len(NEGATIVES_B)}，去重后）")
    print("\n绝对分数 top1：")
    describe("正例", [s for s, _ in pos])
    describe("负例", [s for s, _ in neg])

    pos_min = min(s for s, _ in pos)
    neg_max = max(s for s, _ in neg)
    print(f"\n  正例最低 {pos_min:.4f} vs 负例最高 {neg_max:.4f} → "
          + ("区间重叠，单看分数分不开" if neg_max >= pos_min else "分数可以分开"))

    sweep(pos, neg)

    print("\n分差（top1 − top2）：")
    describe("正例", [g for _, g in pos])
    describe("负例", [g for _, g in neg])
    gap_pos_min = min(g for _, g in pos)
    gap_neg_max = max(g for _, g in neg)
    print(f"\n  正例最小分差 {gap_pos_min:.4f} vs 负例最大分差 {gap_neg_max:.4f} → "
          + ("分差能分开" if gap_neg_max < gap_pos_min
             else "分差也分不开"))

    print("\n读数提示：")
    print("  · 换一批负例，负例 top1 的最高值会从 0.171 跳到 0.2014 —— 绝对分数的结论不稳")
    print("  · 分差在两套负例里都稳定（负例 ≤ 0.1205，正例 ≥ 0.1353）—— 这是更可靠的判据")
    print("  · 样本仍小（15 正 + 35 负），只算初步结论；上生产前要按真实流量采样重标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
