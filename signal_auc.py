"""
signal_auc.py:逐个检查「判定信号」有没有分辨力,先别急着投票或定阈值。

用法(放在 campus-rag 文件夹里,和 rag_engine.py、heldout_check.py 同一层):
    python signal_auc.py
    python signal_auc.py --easy-neg my_easy_negatives.txt     # 每行一个离题问题

做什么:
1. 对每个问题,计算 4 个信号:
   - top1      检索最高分
   - gap       top1 - top2 的分差
   - coverage  问句里的实词(按 IDF 加权)有多大比例出现在 top1 块里
   - matched   问句里的实词有几个出现在 top1 块里
2. 用 AUC 衡量每个信号能不能把「正例」和「负例」分开,并用自助法给出 95% 区间:
   AUC = 随机抽一个正例和一个负例,正例的信号值更高的概率。
   0.5 = 和抛硬币一样;越接近 1 越好;区间包含 0.5 说明这批样本看不出分辨力。
3. 分组单独报告,不混在一起:
   - 留出正例(只取 top1 检索正确的) vs 难负例(话题在手册里、这件事没写)
   - 留出正例 vs 离题负例
   - 训练正例(evaluation.py 的 15 题) vs 离题负例  ← 仅作对照,它们和手册一起写,字面重合度偏高

AUC 不需要选阈值,所以不会因为“凑阈值”而虚高。
样本很小,区间会很宽;区间宽本身就是结论,请如实写进页面。
这个脚本只用词面信息、完全离线。我这里没装 jieba,没有用真实分词跑出数字。
"""

import argparse
import logging
import random
import statistics

logging.disable(logging.CRITICAL)

from evaluation import EVAL_CASES
from heldout_check import HARD_NEG, HELDOUT_POS, squash
from rag_engine import _tokenize, load_engine_with_handbook

# 简单停用词:问句里没有区分度的词。可以按需增删。
STOP = set(
    "什么 怎么 怎样 如何 多少 可以 能否 是否 需要 应该 请问 一个 一般 哪些 哪里 为什么 "
    "多久 几天 几点 有没有 要不要 能不能 可不可以 是不是 以及 或者 还是 还有 如果 因为 所以".split()
)
SIGNALS = ["top1", "gap", "coverage", "matched"]


def build_weight(engine):
    vec = engine._vectorizer
    vocab, idf = vec.vocabulary_, vec.idf_
    max_idf = max(idf)

    def weight(token):
        # 手册里从没出现过的词,当作最“稀有”的词:没匹配上,就是该扣的分
        return idf[vocab[token]] if token in vocab else max_idf

    return weight


def signals(engine, weight, question):
    hits = engine.retrieve(question, top_k=2)
    c1, s1 = hits[0]
    gap = s1 - hits[1][1] if len(hits) > 1 else s1

    tokens = [t for t in _tokenize(question.lower()) if len(t) >= 2 and t not in STOP]
    ctx = squash(c1.text).lower()
    w_all = w_hit = 0.0
    n_hit = 0
    for t in dict.fromkeys(tokens):  # 去重但保持顺序
        w = weight(t)
        w_all += w
        if t in ctx:
            w_hit += w
            n_hit += 1
    cov = w_hit / w_all if w_all else 0.0
    return {"top1": s1, "gap": gap, "coverage": cov, "matched": float(n_hit)}, c1


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def bootstrap_ci(pos, neg, n_boot=2000, seed=0):
    rnd = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        p = [rnd.choice(pos) for _ in pos]
        q = [rnd.choice(neg) for _ in neg]
        vals.append(auc(p, q))
    vals.sort()
    return vals[int(0.025 * n_boot)], vals[int(0.975 * n_boot) - 1]


def verdict(lo, hi):
    if lo > 0.5:
        return "有分辨力"
    if hi < 0.5:
        return "方向反了"
    return "区间含 0.5,看不出"


def compare(title, pos_rows, neg_rows):
    print(f"\n【{title}】正例 {len(pos_rows)} 条,负例 {len(neg_rows)} 条")
    if not pos_rows or not neg_rows:
        print("  样本为空,跳过")
        return
    print(f"  {'信号':<9}{'AUC':>6}   {'95% 区间':<14}结论")
    for name in SIGNALS:
        p = [r[name] for r in pos_rows]
        n = [r[name] for r in neg_rows]
        a = auc(p, n)
        lo, hi = bootstrap_ci(p, n)
        print(f"  {name:<9}{a:>6.2f}   [{lo:.2f}, {hi:.2f}]   {verdict(lo, hi)}")


def medians(title, rows):
    if not rows:
        return
    parts = ", ".join(f"{s}={statistics.median(r[s] for r in rows):.3f}" for s in SIGNALS)
    print(f"  {title:<12}中位数:{parts}")


def load_easy_negatives(path):
    """载入离题负例,并打印条数。模块不存在会明说;模块在但变量名不对会直接报错。"""
    if path:
        with open(path, encoding="utf-8") as f:
            qs = [line.strip() for line in f if line.strip()]
        print(f"离题负例:从 {path} 载入 {len(qs)} 条")
        if not qs:
            raise SystemExit("--easy-neg 文件是空的,停止运行")
        return qs
    try:
        from threshold_experiment import NEGATIVES  # ImportError(名字不对)不会被吞掉
    except ModuleNotFoundError:
        print("离题负例:没找到 threshold_experiment.py,也没给 --easy-neg,离题相关对比会被跳过")
        return []
    print(f"离题负例:从 threshold_experiment.NEGATIVES 载入 {len(NEGATIVES)} 条")
    return list(NEGATIVES)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--easy-neg", help="离题负例文件,每行一个问题;不给就尝试用 threshold_experiment.py 里的 NEGATIVES")
    args = ap.parse_args()

    engine = load_engine_with_handbook()
    weight = build_weight(engine)

    held_pos, held_pos_all, wrong = [], [], []
    for q, kws in HELDOUT_POS:
        sig, c1 = signals(engine, weight, q)
        held_pos_all.append(sig)
        if any(k in squash(c1.text) for k in kws):
            held_pos.append(sig)
        else:
            wrong.append(q)

    hard_neg = [signals(engine, weight, q)[0] for q in HARD_NEG]
    easy_list = load_easy_negatives(args.easy_neg)
    easy_neg = [signals(engine, weight, q)[0] for q in easy_list]
    train_pos = [signals(engine, weight, c["question"])[0] for c in EVAL_CASES]

    print(f"留出正例 {len(HELDOUT_POS)} 条,其中 top1 检索正确 {len(held_pos)} 条(判定只用这部分来评)")
    if wrong:
        print("检索没命中的正例(先去看检索,不是判定的问题):")
        for q in wrong:
            print("  -", q)
    if not easy_neg:
        print("提示:没有找到离题负例,相关对比会被跳过。可用 --easy-neg 提供文件。")

    print("\n各组信号中位数(先看一眼分布):")
    medians("留出正例", held_pos)
    medians("难负例", hard_neg)
    medians("离题负例", easy_neg)
    medians("训练正例", train_pos)

    compare("留出正例 vs 难负例(话题在手册里,但这件事没写)", held_pos, hard_neg)
    compare("留出正例 vs 离题负例", held_pos, easy_neg)
    compare("训练正例 vs 离题负例(仅作对照)", train_pos, easy_neg)

    print("\n怎么读:")
    print("- 只有区间下界 > 0.5 的信号,才值得进入下一步;区间含 0.5 的先丢掉,别拿去投票。")
    print("- 如果信号在“离题负例”上有分辨力、在“难负例”上没有,就如实写:")
    print("  词面信号能拦住离题问题,拦不住话题内缺失,后者需要降档提示或更强的模型。")
    print("- 样本太小,区间会很宽。想收窄区间,只能增加新问题(最好别人写),不能靠调参。")


if __name__ == "__main__":
    main()
