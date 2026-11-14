"""校园文档问答前端：上传或使用示例手册，返回答案和引用。"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag_engine import RAGEngine  # noqa: E402

# 生成模块可选：导入失败时用占位函数，侧边栏仍可工作，提问会走抽取式。
try:
    from generator import config_status, is_configured
except Exception:  # noqa: BLE001
    def is_configured() -> bool:  # type: ignore[misc]
        return False

    def config_status() -> str:  # type: ignore[misc]
        return "生成模块不可用，将使用抽取式。"

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "campus_rag.log"


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("campus_rag")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


logger = _setup_logging()

st.set_page_config(page_title="校园文档问答 RAG", page_icon="📘", layout="wide")


def _init_engine() -> RAGEngine:
    if "engine" not in st.session_state:
        st.session_state.engine = RAGEngine()
        st.session_state.doc_label = "尚未加载文档"
        st.session_state.chunk_count = 0
        st.session_state.load_error = ""
    return st.session_state.engine


def _load_handbook() -> None:
    engine: RAGEngine = st.session_state.engine
    try:
        n = engine.load_default_handbook()
        st.session_state.doc_label = "示例：《青禾大学学生手册》"
        st.session_state.chunk_count = n
        st.session_state.load_error = ""
        logger.info("界面加载示例手册 chunks=%d", n)
    except Exception as exc:  # noqa: BLE001
        logger.exception("加载示例手册失败")
        st.session_state.load_error = f"加载示例手册失败：{exc}"


def _load_uploads(files) -> None:
    engine: RAGEngine = st.session_state.engine
    engine.reset()
    total = 0
    names = []
    try:
        for f in files:
            name = f.name
            suffix = Path(name).suffix.lower()
            if suffix not in {".txt", ".md"}:
                raise ValueError(f"暂不支持 {suffix or '无扩展名'} 文件，请上传 .txt 或 .md")
            raw = f.getvalue()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gb18030")
            total += engine.add_document(text, source=name)
            names.append(name)
        st.session_state.doc_label = "已上传：" + "、".join(names)
        st.session_state.chunk_count = total
        st.session_state.load_error = ""
        logger.info("界面加载上传文档 files=%s chunks=%d", names, total)
    except Exception as exc:  # noqa: BLE001
        logger.exception("上传文档失败")
        st.session_state.load_error = f"上传失败：{exc}"
        st.session_state.doc_label = "尚未加载文档"
        st.session_state.chunk_count = 0


def render_sidebar() -> None:
    engine = _init_engine()
    with st.sidebar:
        st.header("文档来源")
        st.caption("先加载文档，再在右侧提问。答案会附带来源引用。")
        if st.button("使用示例校园手册", type="primary", use_container_width=True):
            _load_handbook()
        uploads = st.file_uploader(
            "或上传学生手册（.txt / .md）",
            type=["txt", "md"],
            accept_multiple_files=True,
        )
        if uploads:
            if st.button("用上传文件重建索引", use_container_width=True):
                _load_uploads(uploads)

        st.divider()
        st.subheader("回答方式")
        # 默认选中抽取式，保证没有密钥时也能直接用；此开关只传给 ask(mode=...)，不改变检索。
        mode_label = st.radio(
            "回答方式",
            ["抽取式（默认）", "生成式"],
            index=0,
            label_visibility="collapsed",
        )
        st.session_state.answer_mode = "generative" if mode_label.startswith("生成式") else "extractive"
        if st.session_state.answer_mode == "generative":
            # 仅作配置提示：未配置时不禁止点击提问，真正的回退发生在引擎内部。
            if is_configured():
                st.caption(config_status())
            else:
                st.warning("未检测到 API 密钥或 Ollama。提问时会自动改用抽取式，不影响使用。")
                st.caption("可选配置见项目里的 `.env.example`（复制为 `.env` 后填写）。")
        else:
            st.caption("抽取式从原文句子中挑选答案，不调用外部模型。")

        st.divider()
        st.subheader("检索参数")
        top_k = st.slider("返回依据条数 top_k", min_value=2, max_value=8, value=4, step=1)
        st.session_state.top_k = top_k
        engine.top_k = top_k

        st.divider()
        st.subheader("当前索引")
        st.write(st.session_state.get("doc_label", "尚未加载文档"))
        st.write(f"片段数：{st.session_state.get('chunk_count', 0)}")
        err = st.session_state.get("load_error")
        if err:
            st.error(err)
        st.caption(f"日志文件：`{LOG_FILE}`")
        st.caption("命令行评测门禁：`python evaluation.py`")


def render_citations(title: str, items, key_prefix: str) -> None:
    if not items:
        st.caption("没有可展示的引用。")
        return
    st.markdown(f"**{title}**")
    for i, cit in enumerate(items, start=1):
        with st.expander(f"{i}. {cit.chunk_id} · {cit.section}（相似度 {cit.score:.3f}）", expanded=(i <= 2)):
            st.write(cit.snippet)
            st.caption(f"来源文件：{cit.source}")


def main() -> None:
    render_sidebar()
    st.title("校园文档问答")
    st.write("基于本地 TF-IDF 检索的 RAG 原型：默认从学生手册中抽取答案并展示引用。可在左侧开启生成式；没有密钥时自动退回抽取式。")

    engine: RAGEngine = st.session_state.engine
    if not engine.is_ready():
        st.info("还没有文档。请在左侧点击「使用示例校园手册」，或上传自己的 .txt / .md 文件。")

    examples = [
        "宿舍几点熄灯？大门几点关？",
        "国家奖学金是多少钱？",
        "校园卡丢了怎么补办，工本费多少？",
        "无故缺考怎么处理？",
    ]
    chosen = st.selectbox("可先选一个示例问题", ["（自己输入）"] + examples)
    default_q = "" if chosen == "（自己输入）" else chosen
    question = st.text_area("你的问题", value=default_q, height=90, placeholder="例如：本科生图书馆一次能借几本书？")

    col_a, col_b = st.columns([1, 3])
    with col_a:
        asked = st.button("提问", type="primary", use_container_width=True)
    with col_b:
        if st.session_state.get("answer_mode") == "generative":
            st.caption("生成式会把检索到的依据送给模型组织答案；失败或未配置时自动退回抽取式。")
        else:
            st.caption("当前为抽取式：只依据已加载文档中的原文句子作答。")

    if not asked:
        return
    if not engine.is_ready():
        st.warning("请先加载文档再提问。")
        return

    try:
        with st.spinner("正在检索并组织答案…"):
            # 把侧边栏开关传给引擎；缺省仍是抽取式，避免 session 尚未初始化时误走生成式。
            result = engine.ask(
                question,
                top_k=st.session_state.get("top_k", 4),
                mode=st.session_state.get("answer_mode", "extractive"),
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("界面问答失败")
        st.error(f"系统出错：{exc}")
        with st.expander("错误详情"):
            st.code(traceback.format_exc())
        return

    if result.status == "error":
        st.error(result.error or "提问失败")
        return

    if result.status == "low_confidence":
        st.warning(result.answer)
        render_citations("最接近的原文（不是答案）", result.citations, "weak")
        return

    if result.status == "no_evidence":
        st.warning(result.answer)
        render_citations("检索到的片段（相关度不足）", result.retrieved, "weak")
        return

    st.subheader("答案")
    # 展示实际采用的路径：用户选了生成式但引擎降级时，用警告说明，避免误以为仍是模型作答。
    if result.answer_mode == "generative":
        st.caption("回答方式：生成式")
    elif result.answer_mode == "extractive_fallback":
        st.warning("生成式不可用或调用失败，已自动改用抽取式答案。")
    else:
        st.caption("回答方式：抽取式")
    st.write(result.answer)
    render_citations("引用依据", result.citations, "cite")
    with st.expander("查看全部检索结果"):
        render_citations("本次检索排序", result.retrieved, "all")
    logger.info("界面已返回答案 status=%s q=%r", result.status, question[:40])


if __name__ == "__main__":
    main()
