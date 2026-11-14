"""
run_frozen_test.py:冻结测试集的检查与「只跑一次」的运行器。

文件(都放在 campus-rag 文件夹里,和 rag_engine.py、signal_auc.py 同一层):
    frozen_testset.json   60 道题:30 正例 + 15 离题负例 + 15 话题内缺失负例
    frozen_config.json    你在看任何分数之前定好的信号和三档阈值(自己创建,格式见下)
    frozen_result.json    运行后自动生成

三步用法:
1) 体检(不检索、不出分数,可以随便跑):
       python run_frozen_test.py --check
       python run_frozen_test.py --check --existing-questions my_old_questions.txt
   检查:正例的关键词是否真在手册里、缺失类负例的关键词是否真的不在手册里、
   题目之间和与你已有题目之间有没有重复。体检发现的问题,按人工读手册来改题,
   这一步改题是允许的,因为还没有看过任何分数。

2) 创建 frozen_config.json(在看分数之前!),例如:
       {
         "frozen_at": "git 提交号或日期时间",
         "tiers": {"signal": "gap", "high": 0.20, "low": 0.08}
       }
   signal 可选 top1 / gap / coverage / matched。三档:信号 >= high 为高置信,
   >= low 为低置信,其余为无依据。数字请用开发集(你原来的样本)按事先说好的规则定。

3) 正式运行,只跑一次:
       python run_frozen_test.py
   结果写进 frozen_result.json。再次运行会被拦下;用 --force 重跑,
   结果里会标记 rerun,这样的结果不能再叫“冻结测试”。

我这里没有装 jieba,没有跑出过任何分数,题目是在完全不知道分数的情况下写的。
"""

import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTSET = HERE / "frozen_testset.json"
CONFIG = HERE / "frozen_config.json"
RESULT = HERE / "frozen_result.json"
DEFAULT_HANDBOOK = HERE / "data" / "campus_handbook.txt"
SIGNAL_NAMES = ["top1", "gap", "coverage", "matched"]


def squash(text):
    return "".join(text.split())


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, center - half), min(1.0, center + half)


def frac(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n}(95% 区间 {lo:.0%}–{hi:.0%})"


def bigrams(text):
    s = re.sub(r"[\s\W_]+", "", text)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a, b):
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A | B) if (A | B) else 0.0


def load_set():
    return json.loads(TESTSET.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 体检
def existing_questions(extra_file):
    out = []
    try:
        from evaluation import EVAL_CASES
        out += [c["question"] for c in EVAL_CASES]
    except Exception:
        pass
    try:
        from heldout_check import HARD_NEG, HELDOUT_POS
        out += [q for q, _ in HELDOUT_POS] + list(HARD_NEG)
    except Exception:
        pass
    try:
        from threshold_experiment import NEGATIVES
        out += list(NEGATIVES)
    except Exception:
        pass
    if extra_file:
        out += [l.strip() for l in Path(extra_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def check(args):
    data = load_set()
    hb = squash(Path(args.handbook).read_text(encoding="utf-8"))
    problems = []

    pos, off, ind = data["positives"], data["negatives_offtopic"], data["negatives_in_domain"]
    print(f"题量:正例 {len(pos)},离题负例 {len(off)},话题内缺失负例 {len(ind)}")
    if (len(pos), len(off), len(ind)) != (30, 15, 15):
        problems.append("题量不是 30 / 15 / 15")

    for p in pos:
        for kw in p["gold_keywords"]:
            if squash(kw) not in hb:
                problems.append(f"{p['id']} 的关键词不在手册里:{kw}")
    for m in ind:
        for term in m["absent_terms"]:
            if squash(term) in hb:
                problems.append(f"{m['id']} 声称缺失的词其实在手册里:{term}(请人工判断这题是否还算“手册没写”)")

    items = [(x["id"], x["q"]) for x in pos + off + ind]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if similarity(items[i][1], items[j][1]) >= 0.6:
                problems.append(f"{items[i][0]} 与 {items[j][0]} 太相似")

    old = existing_questions(args.existing_questions)
    print(f"用于查重的已有题目:{len(old)} 条")
    for qid, q in items:
        for o in old:
            if similarity(q, o) >= 0.5:
                problems.append(f"{qid} 与已有题目相似:{o}")
                break

    print("\n体检结果:" + ("没有发现问题" if not problems else f"{len(problems)} 个问题"))
    for p in problems:
        print("  -", p)
    print("\n提醒:“手册没写”是人工判断。请自己通读 15 道缺失类负例,觉得手册其实答得了的,")
    print("在看到任何分数之前删掉或改掉。一旦看过分数,就不能再改题。")
    return 1 if problems else 0


# ---------------------------------------------------------------- 正式运行
def tier(value, high, low):
    return "高" if value >= high else ("中" if value >= low else "低")


def run(args):
    if not CONFIG.exists():
        print("找不到 frozen_config.json。请先在看分数之前创建它,格式见本文件开头的说明。")
        return 2
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    t = cfg["tiers"]
    if t["signal"] not in SIGNAL_NAMES:
        print("tiers.signal 必须是:", ", ".join(SIGNAL_NAMES))
        return 2
    prev = None
    if RESULT.exists():
        if not args.force:
            print("frozen_result.json 已存在:冻结测试只能跑一次。")
            print("如果一定要重跑,加 --force,但结果会标记为 rerun,不能再叫冻结测试。")
            return 2
        prev = json.loads(RESULT.read_text(encoding="utf-8"))

    import logging
    logging.disable(logging.CRITICAL)
    from rag_engine import load_engine_with_handbook
    from signal_auc import SIGNALS, auc, bootstrap_ci, build_weight, signals, verdict

    data = load_set()
    engine = load_engine_with_handbook()
    weight = build_weight(engine)

    rows = {"pos": [], "off": [], "ind": []}
    for p in data["positives"]:
        sig, c1 = signals(engine, weight, p["q"])
        top4 = engine.retrieve(p["q"], top_k=4)
        kws = [squash(k) for k in p["gold_keywords"]]
        rows["pos"].append({
            "id": p["id"], "sig": sig,
            "hit1": any(k in squash(c1.text) for k in kws),
            "hit4": any(any(k in squash(c.text) for k in kws) for c, _ in top4),
            "tier": tier(sig[t["signal"]], t["high"], t["low"]),
        })
    for key, name in (("off", "negatives_offtopic"), ("ind", "negatives_in_domain")):
        for n in data[name]:
            sig, _ = signals(engine, weight, n["q"])
            rows[key].append({"id": n["id"], "sig": sig, "tier": tier(sig[t["signal"]], t["high"], t["low"])})

    pos = rows["pos"]
    pos_ok = [r for r in pos if r["hit1"]]
    print(f"冻结测试集 sha256:{sha256(TESTSET)[:16]}…  配置 sha256:{sha256(CONFIG)[:16]}…")
    print(f"\n【检索】hit@1 {frac(sum(r['hit1'] for r in pos), len(pos))};hit@4 {frac(sum(r['hit4'] for r in pos), len(pos))}")

    print("\n【各信号的 AUC(正例只取检索 hit@1 正确的)】")
    groups = {"离题负例": rows["off"], "话题内缺失负例": rows["ind"], "全部负例": rows["off"] + rows["ind"]}
    auc_out = {}
    for gname, neg in groups.items():
        print(f"  正例 {len(pos_ok)} 条 vs {gname} {len(neg)} 条")
        for s in SIGNALS:
            P = [r["sig"][s] for r in pos_ok]
            N = [r["sig"][s] for r in neg]
            a = auc(P, N)
            lo, hi = bootstrap_ci(P, N)
            auc_out[f"{gname}/{s}"] = [round(a, 4), round(lo, 4), round(hi, 4)]
            print(f"    {s:<9}{a:.2f}  [{lo:.2f}, {hi:.2f}]  {verdict(lo, hi)}")

    print(f"\n【三档(信号 {t['signal']},高 >= {t['high']},低 >= {t['low']})】")
    def counts(rs):
        return {k: sum(r["tier"] == k for r in rs) for k in ("高", "中", "低")}
    summary = {}
    for name, rs in (("正例(检索正确)", pos_ok), ("正例(检索错误)", [r for r in pos if not r["hit1"]]),
                     ("离题负例", rows["off"]), ("话题内缺失负例", rows["ind"])):
        c = counts(rs)
        summary[name] = c
        print(f"  {name:<12} 共 {len(rs):>2}:高置信 {c['高']},低置信 {c['中']},无依据 {c['低']}")
    off_c, ind_c = summary["离题负例"], summary["话题内缺失负例"]
    pos_c = summary["正例(检索正确)"]
    print(f"\n  硬答错(负例落入高置信档):离题 {frac(off_c['高'], 15)};话题内缺失 {frac(ind_c['高'], 15)}")
    print(f"  误拒(检索正确的正例落入无依据档):{frac(pos_c['低'], len(pos_ok))}")
    print("  注意:负例 0 次硬答错,只说明硬答错率的上界约 20%(每组 15 条),不能说“没有”。")

    result = {
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "testset_sha256": sha256(TESTSET), "config_sha256": sha256(CONFIG),
        "config": cfg, "rerun": prev is not None,
        "run_count": (prev.get("run_count", 1) + 1) if prev else 1,
        "retrieval": {"hit1": sum(r["hit1"] for r in pos), "hit4": sum(r["hit4"] for r in pos), "n": len(pos)},
        "auc": auc_out, "tiers": summary, "per_question": rows,
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写入 frozen_result.json。" + ("(这是重跑,不能再叫冻结测试)" if prev else "请不要为了结果好看而改题或改配置后重跑。"))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只做题目体检,不检索、不出分数")
    ap.add_argument("--handbook", default=str(DEFAULT_HANDBOOK))
    ap.add_argument("--existing-questions", help="你已有的题目文件(每行一题),用于查重")
    ap.add_argument("--force", action="store_true", help="允许重跑(结果会标记 rerun)")
    args = ap.parse_args()
    sys.exit(check(args) if args.check else run(args))


if __name__ == "__main__":
    main()
