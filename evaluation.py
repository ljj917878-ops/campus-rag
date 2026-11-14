"""校园文档问答评测门禁：固定题集 + 相关性 / 忠实度等简单指标。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from rag_engine import RAGEngine, load_engine_with_handbook

logger = logging.getLogger("campus_rag.eval")

# 忠实度、关键词命中、检索命中的默认通过线（可被命令行覆盖）
DEFAULT_THRESHOLDS = {
    "keyword_hit": 0.60,
    "faithfulness": 0.70,
    "retrieval_hit": 0.70,
    "overall": 0.65,
}


EVAL_CASES = [
    {
        "id": "Q01",
        "question": "新生因故不能按期报到，最多可以请假多久？逾期未报到会怎样？",
        "keywords": ["两周", "取消入学资格"],
        "must_source_hints": ["报到", "入学"],
    },
    {
        "id": "Q02",
        "question": "每学期开学后需要在几个工作日内完成注册？",
        "keywords": ["3 个工作日", "3个工作日"],
        "must_source_hints": ["注册"],
        "keyword_mode": "any",
    },
    {
        "id": "Q03",
        "question": "一学期旷课累计达到 16 学时会受到什么处分？",
        "keywords": ["警告"],
        "must_source_hints": ["旷课", "16 学时", "16学时"],
    },
    {
        "id": "Q04",
        "question": "无故缺考按什么处理？还能参加正常补考吗？",
        "keywords": ["旷考", "0 分", "0分", "不得参加正常补考"],
        "must_source_hints": ["缺考", "旷考"],
        "keyword_mode": "any_groups",
        "keyword_groups": [["旷考"], ["0 分", "0分"], ["不得参加正常补考", "重修"]],
    },
    {
        "id": "Q05",
        "question": "国家奖学金的奖励标准是多少？",
        "keywords": ["8000"],
        "must_source_hints": ["国家奖学金"],
    },
    {
        "id": "Q06",
        "question": "校级综合奖学金一等、二等、三等分别是多少钱？申请有什么成绩要求？",
        "keywords": ["3000", "2000", "1000", "不及格"],
        "must_source_hints": ["综合奖学金"],
    },
    {
        "id": "Q07",
        "question": "宿舍几点熄灯，大门几点关闭？",
        "keywords": ["23:00", "23:30"],
        "must_source_hints": ["熄灯", "大门"],
    },
    {
        "id": "Q08",
        "question": "宿舍里能不能用热得快或电热锅？违规会怎样？",
        "keywords": ["禁止", "警告"],
        "must_source_hints": ["热得快", "电热锅", "电器"],
    },
    {
        "id": "Q09",
        "question": "本科生在图书馆最多可以同时借几册书，借期多少天？",
        "keywords": ["10 册", "10册", "30 天", "30天"],
        "must_source_hints": ["借阅", "借期"],
        "keyword_mode": "any_groups",
        "keyword_groups": [["10 册", "10册"], ["30 天", "30天"]],
    },
    {
        "id": "Q10",
        "question": "校园卡丢了怎么补办，工本费是多少？",
        "keywords": ["挂失", "20 元", "20元"],
        "must_source_hints": ["校园卡", "补办"],
        "keyword_mode": "any_groups",
        "keyword_groups": [["挂失"], ["20 元", "20元"]],
    },
    {
        "id": "Q11",
        "question": "寒暑假想留校住宿要提前多久申请？",
        "keywords": ["7 天", "7天"],
        "must_source_hints": ["留校"],
        "keyword_mode": "any",
    },
    {
        "id": "Q12",
        "question": "校医院工作日的门诊时间是什么时候？急诊电话是多少？",
        "keywords": ["8:00", "11:30", "14:00", "17:30", "120-8810"],
        "must_source_hints": ["校医院", "急诊"],
    },
    {
        "id": "Q13",
        "question": "成立学生社团至少需要多少名发起成员？要不要指导教师？",
        "keywords": ["20 名", "20名", "指导教师"],
        "must_source_hints": ["社团"],
        "keyword_mode": "any_groups",
        "keyword_groups": [["20 名", "20名"], ["指导教师"]],
    },
    {
        "id": "Q14",
        "question": "预期参加人数超过 100 人的大型活动要提前多久报备？",
        "keywords": ["10 个工作日", "10个工作日"],
        "must_source_hints": ["100 人", "100人", "报备"],
        "keyword_mode": "any",
    },
    {
        "id": "Q15",
        "question": "成绩有异议的话，必须在成绩公布后多少个工作日内申请复核？",
        "keywords": ["5 个工作日", "5个工作日"],
        "must_source_hints": ["成绩", "复核"],
        "keyword_mode": "any",
    },
]


@dataclass
class CaseScore:
    case_id: str
    question: str
    answer: str
    status: str
    keyword_hit: float
    faithfulness: float
    retrieval_hit: float
    relevance: float
    overall: float
    missing_keywords: list[str]
    citations: list[str]
    error: str | None = None


def _flatten_text(*parts: str) -> str:
    return "".join(parts).replace(" ", "").replace("\n", "")


def _keyword_score(answer: str, case: dict) -> tuple[float, list[str]]:
    text = answer or ""
    compact = _flatten_text(text)
    mode = case.get("keyword_mode", "all")
    if mode == "any_groups":
        groups = case.get("keyword_groups") or [[kw] for kw in case["keywords"]]
        hits = 0
        missing: list[str] = []
        for group in groups:
            if any(_flatten_text(k) in compact or k in text for k in group):
                hits += 1
            else:
                missing.append("/".join(group))
        return (hits / len(groups) if groups else 0.0), missing
    keywords = list(case.get("keywords") or [])
    if mode == "any":
        ok = any(_flatten_text(k) in compact or k in text for k in keywords)
        return (1.0 if ok else 0.0), ([] if ok else keywords)
    missing = [k for k in keywords if _flatten_text(k) not in compact and k not in text]
    hit = (len(keywords) - len(missing)) / len(keywords) if keywords else 0.0
    return hit, missing


def _faithfulness(answer: str, context: str) -> float:
    """答案中的实质片段应能在检索上下文中找到，避免胡编。"""
    import jieba  # 局部导入，避免脚本头依赖混乱

    ans = (answer or "").split("（依据：")[0].strip()
    if not ans:
        return 0.0
    ctx = context or ""
    if not ctx:
        return 0.0
    # 以句子为单位：每句至少有一部分出现在上下文中
    sentences = [s.strip() for s in __import__("re").split(r"(?<=[。！？；!?\n])", ans) if s.strip()]
    if not sentences:
        sentences = [ans]
    ctx_flat = _flatten_text(ctx)
    sent_hits = 0
    for sent in sentences:
        flat = _flatten_text(sent)
        if len(flat) < 4:
            continue
        # 滑窗：任一 8 字片段命中上下文即算该句有依据
        window = 8 if len(flat) >= 8 else max(4, len(flat))
        ok = any(flat[i : i + window] in ctx_flat for i in range(0, max(1, len(flat) - window + 1)))
        if ok:
            sent_hits += 1
    usable = [s for s in sentences if len(_flatten_text(s)) >= 4]
    if not usable:
        return 0.0
    sentence_score = sent_hits / len(usable)

    tokens = [t for t in jieba.lcut(ans) if t.strip() and t not in "的了和与或及在是为，。！？、；：（）"]
    if not tokens:
        return sentence_score
    token_hits = sum(1 for t in tokens if t in ctx)
    token_score = token_hits / len(tokens)
    return round(0.7 * sentence_score + 0.3 * token_score, 4)


def _retrieval_hit(context: str, case: dict) -> float:
    """在完整检索段落中检查是否覆盖预期线索（同义写法按 OR 计）。"""
    hints = case.get("must_source_hints") or []
    if not hints:
        return 1.0
    blob = context or ""
    compact = _flatten_text(blob)
    # 将仅空格差异的线索合并为同一组
    groups: list[list[str]] = []
    for h in hints:
        flat = _flatten_text(h)
        placed = False
        for g in groups:
            if _flatten_text(g[0]) == flat:
                g.append(h)
                placed = True
                break
        if not placed:
            groups.append([h])
    hits = 0
    for group in groups:
        if any(_flatten_text(h) in compact or h in blob for h in group):
            hits += 1
    return hits / len(groups) if groups else 0.0


def score_case(engine: RAGEngine, case: dict, top_k: int) -> CaseScore:
    result = engine.ask(case["question"], top_k=top_k)
    context = "\n".join(c.snippet for c in (result.retrieved or []))
    # 忠实度对照完整命中段落，而不仅是摘要
    from rag_engine import RAGEngine as _  # noqa: F401

    full_context = ""
    try:
        hits = engine.retrieve(case["question"], top_k=top_k)
        full_context = "\n".join(chunk.text for chunk, _s in hits)
    except Exception:  # noqa: BLE001
        full_context = context

    kw, missing = _keyword_score(result.answer, case)
    faith = _faithfulness(result.answer, full_context)
    retr = _retrieval_hit(full_context or context, case)
    relevance = round(0.6 * kw + 0.4 * retr, 4)
    overall = round(0.4 * kw + 0.35 * faith + 0.25 * retr, 4)
    if result.status == "error":
        overall = 0.0
    return CaseScore(
        case_id=case["id"],
        question=case["question"],
        answer=result.answer,
        status=result.status,
        keyword_hit=round(kw, 4),
        faithfulness=round(faith, 4),
        retrieval_hit=round(retr, 4),
        relevance=relevance,
        overall=overall,
        missing_keywords=missing,
        citations=[c.chunk_id for c in result.citations],
        error=result.error,
    )


def evaluate(engine: RAGEngine | None = None, top_k: int = 4) -> dict:
    if engine is None:
        engine = load_engine_with_handbook(top_k=top_k)
    rows = [score_case(engine, case, top_k=top_k) for case in EVAL_CASES]
    n = len(rows)
    avg = {
        "keyword_hit": round(sum(r.keyword_hit for r in rows) / n, 4),
        "faithfulness": round(sum(r.faithfulness for r in rows) / n, 4),
        "retrieval_hit": round(sum(r.retrieval_hit for r in rows) / n, 4),
        "relevance": round(sum(r.relevance for r in rows) / n, 4),
        "overall": round(sum(r.overall for r in rows) / n, 4),
    }
    return {"cases": [asdict(r) for r in rows], "average": avg, "count": n}


def gate_passed(average: dict, thresholds: dict) -> tuple[bool, list[str]]:
    failed = []
    for key in ("keyword_hit", "faithfulness", "retrieval_hit", "overall"):
        if average.get(key, 0) < thresholds[key]:
            failed.append(f"{key}={average.get(key)} < {thresholds[key]}")
    return (len(failed) == 0), failed


def _print_report(report: dict, thresholds: dict) -> bool:
    print(f"评测题目数：{report['count']}")
    print("-" * 72)
    print(f"{'ID':<5}{'关键词':<8}{'忠实度':<8}{'检索':<8}{'综合':<8}状态")
    for row in report["cases"]:
        print(
            f"{row['case_id']:<5}{row['keyword_hit']:<8.2f}{row['faithfulness']:<8.2f}"
            f"{row['retrieval_hit']:<8.2f}{row['overall']:<8.2f}{row['status']}"
        )
        if row["missing_keywords"]:
            print(f"     缺失关键词：{', '.join(row['missing_keywords'])}")
        if row["error"]:
            print(f"     错误：{row['error']}")
    print("-" * 72)
    avg = report["average"]
    print(
        "平均分  "
        f"关键词 {avg['keyword_hit']:.2f}  "
        f"忠实度 {avg['faithfulness']:.2f}  "
        f"检索 {avg['retrieval_hit']:.2f}  "
        f"相关性 {avg['relevance']:.2f}  "
        f"综合 {avg['overall']:.2f}"
    )
    passed, failed = gate_passed(avg, thresholds)
    if passed:
        print("门禁结果：通过")
    else:
        print("门禁结果：未通过")
        for item in failed:
            print(f"  - {item}")
    return passed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校园文档问答 RAG 评测门禁")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--json", dest="json_path", default="", help="把完整结果写入 JSON 文件")
    parser.add_argument("--keyword-threshold", type=float, default=DEFAULT_THRESHOLDS["keyword_hit"])
    parser.add_argument("--faithfulness-threshold", type=float, default=DEFAULT_THRESHOLDS["faithfulness"])
    parser.add_argument("--retrieval-threshold", type=float, default=DEFAULT_THRESHOLDS["retrieval_hit"])
    parser.add_argument("--overall-threshold", type=float, default=DEFAULT_THRESHOLDS["overall"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    try:
        report = evaluate(top_k=args.top_k)
    except Exception as exc:  # noqa: BLE001
        logger.exception("评测执行失败")
        print(f"评测失败：{exc}", file=sys.stderr)
        return 2

    thresholds = {
        "keyword_hit": args.keyword_threshold,
        "faithfulness": args.faithfulness_threshold,
        "retrieval_hit": args.retrieval_threshold,
        "overall": args.overall_threshold,
    }
    passed = _print_report(report, thresholds)
    if args.json_path:
        path = Path(args.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"详细结果已写入 {path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
