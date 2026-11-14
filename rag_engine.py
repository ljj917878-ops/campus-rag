"""校园文档问答 RAG 引擎：切分、TF-IDF 检索、抽取式回答与引用。

核心流程图见同目录 FLOW.md（整体问答、ask 决策、评测门禁）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import jieba
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("campus_rag")

DEFAULT_HANDBOOK = Path(__file__).resolve().parent / "data" / "campus_handbook.txt"
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?\n])")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    source: str
    section: str
    start_char: int
    end_char: int


@dataclass
class Citation:
    chunk_id: str
    source: str
    section: str
    snippet: str
    score: float


@dataclass
class AnswerResult:
    question: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    retrieved: list[Citation] = field(default_factory=list)
    status: str = "ok"
    error: str | None = None
    # 实际采用的作答路径：extractive / generative / extractive_fallback（生成失败后的降级）
    answer_mode: str = "extractive"
    # 置信档位：high（照常作答）/ medium（问句实词只命中 1 个，给最接近原文并提示）/ low（一个都没命中，拒答）
    tier: str = "high"

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "status": self.status,
            "error": self.error,
            "answer_mode": self.answer_mode,
            "tier": self.tier,
            "citations": [asdict(c) for c in self.citations],
            "retrieved": [asdict(c) for c in self.retrieved],
        }



# 问句里的高频疑问词，含区分度的实词才算命中。
STOP_TERMS = set(
    "什么 怎么 怎样 如何 多少 可以 能否 是否 需要 应该 请问 一个 一般 哪些 哪里 为什么 "
    "多久 几天 几点 有没有 要不要 能不能 可不可以 是不是 以及 或者 还是 还有 如果 因为 所以".split()
)

# 开发集上按事先规则定出：matched 是开发集里对难负例 AUC 最高的信号（0.87）。
# low = 开发集正例的 10% 分位 = 1，high = 开发负例最大值 = 2。规则与数字见 experiments/dev_thresholds.py
TIER_HIGH = 2
TIER_MEDIUM = 1


def _content_terms(question: str) -> list[str]:
    """问句里长度 ≥2、且不是疑问词的实词，去重保序。"""
    terms = [t for t in _tokenize(question.lower()) if len(t) >= 2 and t not in STOP_TERMS]
    return list(dict.fromkeys(terms))


def _matched_terms(question: str, chunk_text: str) -> int:
    ctx = re.sub(r"\s+", "", _normalize_whitespace(chunk_text)).lower()
    return sum(1 for t in _content_terms(question) if t in ctx)

def _tokenize(text: str) -> list[str]:
    return [tok.strip() for tok in jieba.lcut(text) if tok.strip() and not tok.isspace()]


def _jieba_analyzer(text: str) -> list[str]:
    tokens = _tokenize(text.lower())
    # 对中文再加上 2-gram，缓解专有词切分误差
    grams = []
    compact = re.sub(r"\s+", "", text.lower())
    for i in range(max(0, len(compact) - 1)):
        grams.append(compact[i : i + 2])
    return tokens + grams


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).replace("\r\n", "\n").strip()


def _guess_section(block: str, fallback: str) -> str:
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(第[一二三四五六七八九十百零\d]+[章节条].*)$", line):
            return line[:40]
        if re.match(r"^[一二三四五六七八九十]+、", line) or re.match(r"^附则", line):
            return line[:40]
        return line[:40]
    return fallback


_ARTICLE_SPLIT = re.compile(r"(?=第[一二三四五六七八九十百零\d]+条)")


def _units_of(para: str, chunk_size: int) -> list[str]:
    """把一段拆成「不被切断的最小单位」：优先条，条太长再按句子，句子还太长才按字符。

    这样保证切点只出现在条与条之间、句号之后，不会出现「…没收器具并视」这种半句。
    """
    units: list[str] = []
    for art in _ARTICLE_SPLIT.split(para):
        if not art.strip():
            continue
        if len(art) <= chunk_size:
            units.append(art)
            continue
        for sent in _SENTENCE_SPLIT.split(art):
            if not sent.strip():
                continue
            if len(sent) <= chunk_size:
                units.append(sent)
            else:  # 极端情况：单句超过块上限，只能硬切
                for off in range(0, len(sent), chunk_size):
                    units.append(sent[off : off + chunk_size])
    return units


def _pack_sentences(para: str, chunk_size: int, overlap: int) -> list[tuple[str, int]]:
    """把最小单位打包成若干块，返回 [(块文本, 段内偏移)]。

    - 切点只落在条与条之间或句号之后；
    - 相邻块之间保留至多 overlap 个字符的整单位重叠，用来救边界。
    """
    units = _units_of(para, chunk_size)
    if not units:
        return []

    pieces: list[list[str]] = []
    buf: list[str] = []
    size = 0
    for unit in units:
        if buf and size + len(unit) > chunk_size:
            pieces.append(buf)
            tail: list[str] = []
            tail_size = 0
            for back in reversed(buf):
                if tail_size + len(back) <= overlap:
                    tail.insert(0, back)
                    tail_size += len(back)
                else:
                    break
            buf = tail[:]
            size = tail_size
        buf.append(unit)
        size += len(unit)
    if buf:
        pieces.append(buf)

    out: list[tuple[str, int]] = []
    cursor = 0
    for group in pieces:
        text = "".join(group).strip()
        if not text:
            continue
        idx = para.find(text, cursor)
        if idx < 0:
            idx = cursor
        out.append((text, idx))
        cursor = idx + len(text)
    return out


def split_into_chunks(text: str, source: str, chunk_size: int = 280, overlap: int = 60) -> list[Chunk]:
    """按段落优先切分；长段落按句子边界打包，不切断句子。"""
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正整数")
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 5)

    text = _normalize_whitespace(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    raw_units: list[tuple[str, int]] = []
    cursor = 0
    for para in paragraphs:
        idx = text.find(para, cursor)
        if idx < 0:
            idx = cursor
        raw_units.append((para, idx))
        cursor = idx + len(para)

    chunks: list[Chunk] = []
    current_section = Path(source).name
    seq = 1
    for para, start in raw_units:
        section_hit = _guess_section(para, current_section)
        if re.match(r"^(第[一二三四五六七八九十百零\d]+[章节].*)", section_hit) or section_hit.startswith("附则"):
            current_section = section_hit
        if len(para) <= chunk_size:
            pieces = [(para, 0)]
        else:
            pieces = _pack_sentences(para, chunk_size, overlap)
        for piece, off in pieces:
            chunks.append(
                Chunk(
                    chunk_id=f"{Path(source).stem}-{seq:03d}",
                    text=piece,
                    source=source,
                    section=_guess_section(piece, current_section),
                    start_char=start + off,
                    end_char=start + off + len(piece),
                )
            )
            seq += 1
    logger.info("文档切分完成 source=%s chunks=%d", source, len(chunks))
    return chunks


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    if not parts:
        return [text.strip()] if text.strip() else []
    return parts


def _best_sentence(question: str, text: str) -> str:
    """从块里挑与问句实词重合最多的一句原文；都不含实词就取第一句。"""
    terms = _content_terms(question)
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        return text.strip()
    best, best_hit = sentences[0], -1
    for s in sentences:
        hit = sum(1 for t in terms if t in s.lower())
        if hit > best_hit:
            best, best_hit = s, hit
    return best


def _snippet(text: str, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


_HEADING_ONLY = re.compile(
    r"^(第[一二三四五六七八九十百零\d]+章\S{0,20}|附则|青禾大学学生手册.*)$"
)


def _is_heading(text: str) -> bool:
    compact = re.sub(r"\s+", "", text).strip("。；; ")
    return bool(_HEADING_ONLY.match(compact))


class RAGEngine:
    """基于 TF-IDF 的检索增强问答引擎，答案从原文句子抽取，不依赖外部 API。"""

    def __init__(self, chunk_size: int = 280, overlap: int = 60, top_k: int = 4) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.top_k = top_k
        self.chunks: list[Chunk] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self.sources: list[str] = []

    def reset(self) -> None:
        self.chunks = []
        self._vectorizer = None
        self._matrix = None
        self.sources = []
        logger.info("引擎已重置")

    def add_document(self, text: str, source: str) -> int:
        text = text or ""
        if not text.strip():
            raise ValueError(f"文档为空：{source}")
        new_chunks = split_into_chunks(text, source, self.chunk_size, self.overlap)
        if not new_chunks:
            raise ValueError(f"未能从文档中切分出有效段落：{source}")
        self.chunks.extend(new_chunks)
        if source not in self.sources:
            self.sources.append(source)
        self._fit()
        return len(new_chunks)

    def load_text_file(self, path: str | Path, encoding: str = "utf-8") -> int:
        path = Path(path)
        try:
            raw = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            raw = path.read_text(encoding="gb18030")
            logger.warning("文件 %s 以 gb18030 解码", path)
        return self.add_document(raw, source=path.name)

    def load_default_handbook(self) -> int:
        if not DEFAULT_HANDBOOK.is_file():
            raise FileNotFoundError(f"找不到示例手册：{DEFAULT_HANDBOOK}")
        self.reset()
        n = self.load_text_file(DEFAULT_HANDBOOK)
        logger.info("已加载示例手册 chunks=%d", n)
        return n

    def is_ready(self) -> bool:
        return bool(self.chunks) and self._matrix is not None

    def _fit(self) -> None:
        corpus = [c.text for c in self.chunks]
        self._vectorizer = TfidfVectorizer(
            analyzer=_jieba_analyzer,
            min_df=1,
            sublinear_tf=True,
            norm="l2",
        )
        self._matrix = self._vectorizer.fit_transform(corpus)
        logger.debug("向量索引已更新 documents=%d terms=%d", len(corpus), len(self._vectorizer.get_feature_names_out()))

    def retrieve(self, question: str, top_k: int | None = None) -> list[tuple[Chunk, float]]:
        if not self.is_ready() or self._vectorizer is None or self._matrix is None:
            raise RuntimeError("尚未加载任何文档，无法检索")
        q = (question or "").strip()
        if not q:
            raise ValueError("问题不能为空")
        k = top_k or self.top_k
        k = max(1, min(k, len(self.chunks)))
        q_vec = self._vectorizer.transform([q])
        scores = cosine_similarity(q_vec, self._matrix).ravel()
        order = np.argsort(scores)[::-1][:k]
        hits = [(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]
        if not hits:
            # 即使相似度为 0，也返回最高分片段，便于前端提示
            hits = [(self.chunks[int(order[0])], float(scores[int(order[0])]))]
        logger.info("检索完成 question=%r hits=%s", q[:40], [(h[0].chunk_id, round(h[1], 3)) for h in hits])
        return hits

    # ask() 决策摘要（完整图见 FLOW.md）：
    # 校验问题与索引 → retrieve → 依据不足则 no_evidence（不调用模型）
    # → 抽取式：直接抽句；生成式：先尝试模型，失败或未配置则回退抽句
    # → 返回答案、引用，以及 answer_mode（extractive / generative / extractive_fallback）
    def ask(
        self,
        question: str,
        top_k: int | None = None,
        min_score: float = 0.02,
        mode: str = "extractive",
    ) -> AnswerResult:
        """检索后组织答案。

        mode 只影响「如何写答案」，不影响检索：
        - extractive（默认）：从命中原文中抽句拼接
        - generative：把命中段落交给 generator.py；未配置或调用失败则回退抽取式
        无论哪种模式，相似度过低时都直接返回 no_evidence，不会调用生成式，避免无依据胡编。
        """
        q = (question or "").strip()
        if not q:
            return AnswerResult(question=question or "", answer="", status="error", error="请输入问题后再提问。")
        if not self.is_ready():
            return AnswerResult(question=q, answer="", status="error", error="还没有加载文档，请先选择示例手册或上传文件。")
        try:
            hits = self.retrieve(q, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.exception("检索失败")
            return AnswerResult(question=q, answer="", status="error", error=f"检索失败：{exc}")

        retrieved = [
            Citation(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                section=chunk.section,
                snippet=_snippet(chunk.text),
                score=round(score, 4),
            )
            for chunk, score in hits
        ]
        # 先过滤低相关片段：依据不足时到此结束，不进入生成式。
        strong = [(c, s) for c, s in hits if s >= min_score]
        if not strong:
            return AnswerResult(
                question=q,
                answer="根据当前文档，没有找到足够相关的依据，建议换个问法或检查上传的材料是否包含相关条款。",
                citations=[],
                retrieved=retrieved,
                status="no_evidence",
                tier="low",
            )

        # 三档判定：先数问句实词在 top1 块里命中几个。
        # matched = 0 → 一个都没命中，判 low，直接拒答；
        # matched = 1 → 只沾到一个词，判 medium，给最接近的原文并明确提示「没有直接写」；
        # matched ≥ 2 → 判 high，照常组织答案。
        top_chunk = hits[0][0]
        matched = _matched_terms(q, top_chunk.text)
        tier = "high" if matched >= TIER_HIGH else ("medium" if matched >= TIER_MEDIUM else "low")
        logger.info("判定档位 tier=%s matched=%d q=%r", tier, matched, q[:30])

        if tier == "low":
            return AnswerResult(
                question=q,
                answer="根据当前文档，没有找到足够相关的依据，建议换个问法或检查上传的材料是否包含相关条款。",
                citations=[],
                retrieved=retrieved,
                status="no_evidence",
                tier="low",
            )

        if tier == "medium":
            # 只沾到一个实词：不拼答案，直接把最接近的一句原文摆出来，并说清这是「最接近」不是「答案」。
            nearest = _best_sentence(q, top_chunk.text)
            return AnswerResult(
                question=q,
                answer=(
                    "手册里没有直接写这件事。最接近的原文是：\n\n"
                    f"{nearest}\n\n"
                    "这条只能当参考，不是我查到的规定；如果事情重要，建议直接问辅导员或对应部门。"
                ),
                citations=[
                    Citation(
                        chunk_id=top_chunk.chunk_id,
                        source=top_chunk.source,
                        section=top_chunk.section,
                        snippet=_snippet(nearest),
                        score=round(hits[0][1], 4),
                    )
                ],
                retrieved=retrieved,
                status="low_confidence",
                answer_mode="extractive",
                tier="medium",
            )

        # 生成式是可选项：开关打开才尝试；返回空答案视为需要降级。
        use_generative = (mode or "extractive").strip().lower() in {"generative", "generate", "llm"}
        answer_mode = "extractive"
        used: list[tuple[Chunk, float, str]] = []
        answer = ""
        try:
            if use_generative:
                answer, used, answer_mode = self._try_generative_answer(q, strong)
            # 默认抽取式，或生成式未产出文本时，统一走原文抽句，保证无密钥也能回答。
            if not answer:
                answer, used = self._compose_answer(q, strong)
                if use_generative:
                    answer_mode = "extractive_fallback"
                else:
                    answer_mode = "extractive"
        except Exception as exc:  # noqa: BLE001
            logger.exception("组织答案失败")
            return AnswerResult(
                question=q,
                answer="",
                citations=retrieved,
                retrieved=retrieved,
                status="error",
                error=f"组织答案失败：{exc}",
                answer_mode="error",
            )

        citations = [
            Citation(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                section=chunk.section,
                snippet=_snippet(sent if sent else chunk.text),
                score=round(score, 4),
            )
            for chunk, score, sent in used
        ]
        # 去重但保留顺序
        seen: set[str] = set()
        unique_citations: list[Citation] = []
        for cit in citations:
            key = cit.chunk_id
            if key in seen:
                continue
            seen.add(key)
            unique_citations.append(cit)

        return AnswerResult(
            question=q,
            answer=answer,
            citations=unique_citations,
            retrieved=retrieved,
            status="ok",
            answer_mode=answer_mode,
            tier="high",
        )

    def _try_generative_answer(
        self, question: str, hits: Sequence[tuple[Chunk, float]]
    ) -> tuple[str, list[tuple[Chunk, float, str]], str]:
        """尝试生成式作答；未配置或失败时返回空答案，由 ask() 回退抽取式。

        这里捕获导入失败、未配置、接口异常三类情况，一律返回空字符串而不是抛给上层，
        这样界面不会因为缺密钥或网络问题而中断，只会看到降级后的抽取式答案。
        """
        # 延迟导入，避免未安装 openai 时连抽取式主流程都加载失败。
        try:
            from generator import generate_answer, is_configured
        except Exception as exc:  # noqa: BLE001
            logger.warning("无法导入生成模块，回退抽取式：%s", exc)
            return "", [], "extractive_fallback"

        if not is_configured():
            logger.info("生成式未配置，回退抽取式")
            return "", [], "extractive_fallback"

        # 传给模型的是完整命中段落，而不是界面上的短摘要，以免关键数字被截断。
        contexts = [chunk.text for chunk, _score in hits]
        try:
            answer = generate_answer(question, contexts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成式调用失败，回退抽取式：%s", exc)
            return "", [], "extractive_fallback"

        # 生成式引用对应本次送入模型的全部依据片段，便于对照原文。
        used = [(chunk, score, chunk.text) for chunk, score in hits]
        return answer, used, "generative"

    def _compose_answer(self, question: str, hits: Sequence[tuple[Chunk, float]]) -> tuple[str, list[tuple[Chunk, float, str]]]:
        """从命中段落中抽取与问题最相关的句子，拼成可读答案。"""
        candidates: list[tuple[str, Chunk, float]] = []
        for chunk, score in hits:
            sentences = _split_sentences(chunk.text)
            if not sentences:
                continue
            # 段落本身也作为候选，避免短条款被切碎
            for sent in sentences:
                if len(sent) < 6 or _is_heading(sent):
                    continue
                candidates.append((sent, chunk, score))

        if not candidates:
            chunk, score = hits[0]
            return chunk.text.strip(), [(chunk, score, chunk.text.strip())]

        sent_texts = [c[0] for c in candidates]
        vec = TfidfVectorizer(analyzer=_jieba_analyzer, min_df=1, sublinear_tf=True, norm="l2")
        try:
            mat = vec.fit_transform(sent_texts + [question])
        except ValueError:
            chunk, score = hits[0]
            return chunk.text.strip(), [(chunk, score, chunk.text.strip())]

        qv = mat[-1]
        sm = cosine_similarity(qv, mat[:-1]).ravel()
        # 结合检索分，避免只看句子字面重合
        combined = sm + 0.15 * np.array([c[2] for c in candidates], dtype=float)
        ranked_idx = np.argsort(combined)[::-1]

        picked: list[tuple[Chunk, float, str]] = []
        seen_sent: set[str] = set()
        pieces: list[str] = []
        for i in ranked_idx:
            if combined[i] <= 0:
                break
            sent, chunk, score = candidates[int(i)]
            key = re.sub(r"\s+", "", sent)
            if key in seen_sent:
                continue
            # 已选句子已覆盖该句大部分字时跳过，换一条信息量更高的
            if any(key[:18] in seen or seen[:18] in key for seen in seen_sent if len(seen) >= 18 or len(key) >= 18):
                continue
            seen_sent.add(key)
            ending = "。" if not sent.endswith(("。", "！", "？", ".", "!", "?", "；", ";")) else ""
            pieces.append(sent + ending)
            picked.append((chunk, score, sent))
            if len(pieces) >= 4:
                break

        if not pieces:
            chunk, score = hits[0]
            return chunk.text.strip(), [(chunk, score, chunk.text.strip())]

        answer = "".join(pieces)
        refs = "、".join(dict.fromkeys(p[0].chunk_id for p in picked))
        answer = f"{answer}\n\n（依据：{refs}）"
        return answer, picked


def load_engine_with_handbook(top_k: int = 4) -> RAGEngine:
    engine = RAGEngine(top_k=top_k)
    engine.load_default_handbook()
    return engine
