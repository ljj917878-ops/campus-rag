"""
留出测试:检验「分差规则」和「0.02 门槛」在没参与调参的新问题上靠不靠谱。

用法(放在 campus-rag 文件夹里,和 rag_engine.py 同一层):
    python heldout_check.py
    python heldout_check.py --gap 0.13 --min-score 0.02

为什么需要它:
- 分差阈值 0.13 是在 15 个正例 + 34 个负例上找出来的,没有在新问题上验证过。
- 这里的正例换了问法(比如“缺考”问成“没去参加考试”),负例是「手册有这个话题、
  但没写这件事」的难负例(比如“校医院周末开不开门”),比“火锅店”“天气”难得多。
- 还会标出「top1 和 top2 两块文字有重叠」的问题:切块有 60 字重叠,
  答案正好落在重叠区时,top1 与 top2 很接近,分差规则可能把它误拒。

重要:
- 运行前,请自己对照手册确认每个负例真的没有答案、每个正例的关键词真的在手册里。
- 样本很小,结果只能算初步结论。可以自己继续往下面两个列表里加问题。
"""

import argparse
import logging

logging.disable(logging.CRITICAL)  # 关掉引擎日志,让输出干净

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag_engine import load_engine_with_handbook

# 正例:(换了问法的问题, 正确的块里应该出现的关键词;去掉空格后比较)
HELDOUT_POS = [
    ("没去参加考试会怎么算成绩?", ["旷考"]),
    ("我对分数有疑问,多久之内要提出复核?", ["5个工作日"]),
    ("晚上宿舍几点断电?", ["熄灯"]),
    ("放寒假想住在学校要提前几天说?", ["提前7天"]),
    ("借书能借多久,可以续借吗?", ["借期30天"]),
    ("校园卡丢了怎么办,补办要多少钱?", ["20元"]),
    ("社团要成立需要多少发起人?", ["20名发起成员"]),
    ("办大型活动要提前多久报备?", ["10个工作日"]),
    ("毕业论文没通过答辩还有机会吗?", ["补答辩"]),
    ("转专业一般什么时候申请?", ["第二学期"]),
    ("助学贷款的利息谁来出?", ["财政贴息"]),
    ("校内急救电话是多少?", ["120-8810"]),
]

# 难负例:话题在手册里出现过,但这件事手册没写
HARD_NEG = [
    "校医院周末开不开门?",           # 手册只写了工作日时间
    "考研复试要怎么准备?",
    "社团换届选举怎么进行?",
    "宿舍可以养宠物吗?",
    "校外商场能刷校园卡吗?",
    "可以带手机进考场吗?",
    "休学最长可以休多久?",           # 手册提到休学,但没写时长
    "奖学金和助学金能同时拿吗?",
    "洗衣房几点开门?",
    "校园网每月流量限额是多少?",
    "食堂几点开门?",
]


def squash(text):
    return "".join(text.split())


def probe(engine, question):
    """返回 (top1 分数, 分差, top1 块, 两块是否文字重叠)。"""
    hits = engine.retrieve(question, top_k=2)
    c1, s1 = hits[0]
    if len(hits) > 1:
        c2, s2 = hits[1]
        gap = s1 - s2
        overlap = c1.start_char < c2.end_char and c2.start_char < c1.end_char
    else:
        gap, overlap = s1, False
    return s1, gap, c1, overlap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=0.13, help="分差阈值(top1-top2)")
    ap.add_argument("--min-score", type=float, default=0.02, help="绝对分数门槛")
    args = ap.parse_args()

    engine = load_engine_with_handbook()

    print(f"规则 A:top1 >= {args.min_score}    规则 B:分差 >= {args.gap}\n")

    print("【留出正例】应当放行,且 top1 块里要有关键词")
    pos_rows = []
    for q, kws in HELDOUT_POS:
        s1, gap, c1, ov = probe(engine, q)
        correct = any(k in squash(c1.text) for k in kws)
        a, b = s1 >= args.min_score, gap >= args.gap
        pos_rows.append((q, s1, gap, correct, ov, a, b))
        flag = "  <-- 误拒" if not b else ""
        print(f"  top1={s1:.3f} 分差={gap:.3f} 答对={'是' if correct else '否'} "
              f"两块重叠={'是' if ov else '否'} A放行={'是' if a else '否'} B放行={'是' if b else '否'}  {q}{flag}")

    print("\n【难负例】应当拒答")
    neg_rows = []
    for q in HARD_NEG:
        s1, gap, c1, ov = probe(engine, q)
        a, b = s1 >= args.min_score, gap >= args.gap
        neg_rows.append((q, s1, gap, ov, a, b))
        flag = "  <-- 漏网" if b else ""
        print(f"  top1={s1:.3f} 分差={gap:.3f} 两块重叠={'是' if ov else '否'} "
              f"A放行={'是' if a else '否'} B放行={'是' if b else '否'}  {q}{flag}")

    n_pos, n_neg = len(pos_rows), len(neg_rows)
    print("\n【汇总】")
    print(f"  正例:共 {n_pos} 条,top1 答对 {sum(r[3] for r in pos_rows)} 条")
    print(f"  规则 A(0.02):正例放行 {sum(r[5] for r in pos_rows)}/{n_pos},"
          f"难负例被拒 {sum(not r[4] for r in neg_rows)}/{n_neg}")
    print(f"  规则 B(分差):正例放行 {sum(r[6] for r in pos_rows)}/{n_pos},"
          f"难负例被拒 {sum(not r[5] for r in neg_rows)}/{n_neg}")

    wrong_rejected = [r for r in pos_rows if not r[6]]
    ov_wrong = [r for r in wrong_rejected if r[4]]
    print(f"  规则 B 误拒的正例里,有 {len(ov_wrong)}/{len(wrong_rejected)} 条是 top1 与 top2 文字重叠造成的")
    print("\n样本很小,只能算初步结论。如果规则 B 在这里也能同时做到“正例全过、难负例全拒”,")
    print("再把结果和上面这些问题一起写进页面;如果有误拒或漏网,就如实写出来。")


if __name__ == "__main__":
    main()

