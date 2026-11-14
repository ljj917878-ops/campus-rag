# CampusRAG-Eval 核心流程图

本文用 Mermaid 说明三条主路径，便于对照源码阅读。实现细节以 `rag_engine.py`、`app.py`、`generator.py`、`evaluation.py` 为准。

## 1. 整体问答流程

用户在 Streamlit 中加载文档并提问后，系统先建索引、再检索，最后按所选方式组织答案。生成式只在「已有足够依据」时才会被调用。

```mermaid
flowchart TD
    A[开始：打开界面] --> B{加载文档来源}
    B -->|示例手册或上传 txt/md| C[切分文本<br/>段落优先，超长段再按窗口切分]
    C --> D[建立 TF-IDF 索引]
    D --> E[用户输入问题并选择回答方式]
    E --> F[检索 Top-K 相关片段]
    F --> G{依据是否足够}
    G -->|不足| H[返回「依据不足」和检索片段]
    G -->|足够| I{回答方式}
    I -->|抽取式，默认| J[从原文抽句拼接答案]
    I -->|生成式| K[把命中段落送给模型组织答案]
    K -->|成功| L[返回答案 + 引用]
    K -->|未配置或调用失败| J
    J --> L
    H --> M[结束]
    L --> M
```

对应文件：`app.py`（界面与开关）→ `rag_engine.py`（切分、检索、作答）→ `generator.py`（可选生成式）。

## 2. `ask()` 内部决策流程

`mode` 只决定「怎么写答案」，不改变检索。默认是抽取式；生成式失败时自动降级，保证没有密钥也能回答。

```mermaid
flowchart TD
    A["ask(question, mode, top_k)"] --> B{问题是否为空<br/>或尚未加载文档}
    B -->|是| C[返回 status=error]
    B -->|否| D[retrieve 检索 Top-K]
    D --> E{检索是否成功}
    E -->|异常| C
    E -->|成功| F{命中片段相似度<br/>是否达到 min_score}
    F -->|否| G[返回 status=no_evidence<br/>不调用生成式]
    F -->|是| H{mode 是否为 generative}
    H -->|否，默认抽取式| I["_compose_answer()<br/>从原文抽句"]
    I --> J[answer_mode=extractive]
    H -->|是| K["_try_generative_answer()"]
    K --> L{能否生成出答案}
    L -->|导入失败 / 未配置密钥 / 接口异常或空结果| I2["_compose_answer() 抽取式降级"]
    I2 --> M[answer_mode=extractive_fallback]
    L -->|成功| N[answer_mode=generative]
    J --> O[整理引用并返回 status=ok]
    M --> O
    N --> O
```

阅读入口：`rag_engine.py` 中的 `ask()` 与 `_try_generative_answer()`。

## 3. 评测门禁流程

评测脚本默认走抽取式，不依赖外部模型。15 道固定题全部打分后，用平均分和阈值决定退出码，可接入 CI。

```mermaid
flowchart TD
    A["运行 python evaluation.py"] --> B[加载示例手册并建立索引]
    B --> C[逐题调用 ask 默认抽取式<br/>共 15 道固定题]
    C --> D[计算四项指标<br/>关键词覆盖 / 忠实度 / 检索命中 / 综合分]
    D --> E{评测过程是否异常}
    E -->|是| F[退出码 2]
    E -->|否| G{四项平均分是否都达到阈值}
    G -->|是| H[门禁通过，退出码 0]
    G -->|否| I[门禁未通过，退出码 1]
```

默认阈值：关键词 ≥ 0.60，忠实度 ≥ 0.70，检索命中 ≥ 0.70，综合分 ≥ 0.65。可用命令行参数覆盖。
