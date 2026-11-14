"""可选的生成式回答：只用检索到的依据作答，失败由调用方回退到抽取式。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("campus_rag.generator")

_ROOT = Path(__file__).resolve().parent
# 优先读取项目目录下的 .env，方便本地填写密钥；未安装 python-dotenv 时忽略，改用系统环境变量。
try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

# 系统提示词的设计意图：
# 1. 把模型角色限定为「依据内作答」，禁止用外部知识补全校园规章。
# 2. 明确禁止编造数字、时限、处分，避免生成式常见的幻觉。
# 3. 依据不足时必须直说，而不是猜测，便于前端和评测识别。
# 4. 要求简体中文、表述贴近原文；不要自行编造引用编号（引用由检索结果单独展示）。
_SYSTEM_PROMPT = (
    "你是校园规章文档问答助手。"
    "你必须只根据用户提供的【依据】回答问题，不得使用依据之外的知识，不得编造条款、数字、时限或处分。"
    "如果依据中没有足够信息，请直接说明「依据不足，无法从当前材料得出答案」，不要猜测。"
    "回答使用简体中文，简洁完整，关键数字和原文表述保持一致。"
    "不要输出与问题无关的解释，不要编造引用编号。"
)


def _looks_like_ollama(base_url: str) -> bool:
    """根据地址判断是否为本地 Ollama 的 OpenAI 兼容接口。"""
    value = (base_url or "").lower()
    return "11434" in value or "ollama" in value


def get_llm_config() -> dict[str, str]:
    """读取环境变量，返回 api_key / base_url / model。

    读取优先级说明：
    - 密钥：OPENAI_API_KEY → DEEPSEEK_API_KEY → DASHSCOPE_API_KEY → CAMPUS_RAG_API_KEY
    - 地址：OPENAI_BASE_URL → CAMPUS_RAG_BASE_URL；若都未填，再根据 CAMPUS_RAG_LLM 或专用密钥推断
    - 模型：OPENAI_MODEL → CAMPUS_RAG_MODEL；仍为空时按接口类型给默认模型名
    这样同一套 OpenAI SDK 可以对接 DeepSeek、通义兼容模式或本地 Ollama。
    """
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("CAMPUS_RAG_API_KEY")
        or ""
    ).strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("CAMPUS_RAG_BASE_URL") or "").strip()
    model = (os.getenv("OPENAI_MODEL") or os.getenv("CAMPUS_RAG_MODEL") or "").strip()
    provider = (os.getenv("CAMPUS_RAG_LLM") or "").strip().lower()

    # 未显式给出 base_url 时，用提供商标识或「只配置了专用密钥」来推断默认地址。
    if not base_url:
        if provider == "ollama":
            base_url = "http://127.0.0.1:11434/v1"
        elif provider == "deepseek" or (os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_KEY")):
            base_url = "https://api.deepseek.com"
        elif provider in {"dashscope", "qwen", "tongyi"} or (
            os.getenv("DASHSCOPE_API_KEY") and not os.getenv("OPENAI_API_KEY")
        ):
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Ollama 的兼容接口通常不需要真实密钥，SDK 却要求传 api_key，因此用占位值 "ollama"。
    if _looks_like_ollama(base_url) or provider == "ollama":
        if not base_url:
            base_url = "http://127.0.0.1:11434/v1"
        if not api_key:
            api_key = "ollama"
        if not model:
            model = "qwen2.5:3b"

    if not model:
        lowered = base_url.lower()
        if "deepseek" in lowered:
            model = "deepseek-chat"
        elif "dashscope" in lowered:
            model = "qwen-turbo"
        elif base_url:
            model = "gpt-4o-mini"
        else:
            model = "gpt-4o-mini"

    return {"api_key": api_key, "base_url": base_url, "model": model}


def is_configured() -> bool:
    """是否已具备调用生成式接口的最小配置。

    云端接口必须有密钥；本地 Ollama 只要能识别到兼容地址（或 CAMPUS_RAG_LLM=ollama）即可。
    未配置时不应在本模块里静默编造答案，而是让引擎回退到抽取式。
    """
    cfg = get_llm_config()
    if _looks_like_ollama(cfg["base_url"]):
        return True
    return bool(cfg["api_key"])


def config_status() -> str:
    """给界面看的简短配置说明，只展示模型和接口地址，不含密钥本身。"""
    if not is_configured():
        return "未检测到 API 密钥或 Ollama 地址，生成式将自动退回抽取式。"
    cfg = get_llm_config()
    host = cfg["base_url"] or "https://api.openai.com/v1"
    return f"已配置生成式：模型 {cfg['model']}，接口 {host}"


def _build_user_prompt(question: str, contexts: list[str]) -> str:
    """把问题和检索片段拼成用户提示词，依据按条编号，便于模型对应原文。"""
    blocks = []
    for i, text in enumerate(contexts, start=1):
        piece = (text or "").strip()
        if not piece:
            continue
        blocks.append(f"【依据{i}】\n{piece}")
    evidence = "\n\n".join(blocks) if blocks else "（无依据）"
    return f"问题：{question.strip()}\n\n{evidence}\n\n请只根据以上依据作答。"


def generate_answer(question: str, contexts: list[str], timeout: float = 30.0) -> str:
    """根据依据调用 OpenAI 兼容接口生成答案。

    本函数只负责「能生成就返回文本」：配置缺失、依赖未安装、接口失败或返回空内容时一律抛出异常。
    不在这里做抽取式降级，以便 rag_engine.ask() 统一处理回退，避免两处逻辑不一致。
    """
    q = (question or "").strip()
    if not q:
        raise ValueError("问题不能为空")
    evidence = [c.strip() for c in contexts if (c or "").strip()]
    if not evidence:
        raise ValueError("没有可用于生成的依据")
    if not is_configured():
        raise RuntimeError("未配置生成式接口（缺少 API 密钥或 Ollama 地址）")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("未安装 openai 库，请先执行 pip install -r requirements.txt") from exc

    cfg = get_llm_config()
    client_kwargs: dict = {"api_key": cfg["api_key"], "timeout": timeout}
    # 未设置 base_url 时走 SDK 默认的官方 OpenAI 地址；设置后即可切换到其他兼容服务。
    if cfg["base_url"]:
        client_kwargs["base_url"] = cfg["base_url"]

    logger.info("调用生成式接口 model=%s base_url=%s", cfg["model"], cfg["base_url"] or "default")
    client = OpenAI(**client_kwargs)
    # temperature 取较低值，减少对规章数字和措辞的随意改写。
    response = client.chat.completions.create(
        model=cfg["model"],
        temperature=0.1,
        max_tokens=800,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(q, evidence)},
        ],
    )
    choice = response.choices[0].message if response.choices else None
    text = (choice.content or "").strip() if choice else ""
    if not text:
        raise RuntimeError("生成式接口返回了空答案")
    logger.info("生成式回答完成 chars=%d", len(text))
    return text
