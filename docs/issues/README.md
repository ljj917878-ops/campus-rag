# 已知缺陷清单

这个目录存放每个已知缺陷的完整说明。GitHub 上的 Issue 只保留摘要，细节以此处为准。

| 编号 | 文件 | 一句话 |
|---|---|---|
| 001 | [001-chunking.md](001-chunking.md) | 280 字硬切会把句子截断，chunk 的 section 变成纯标点 |
| 002 | [002-threshold.md](002-threshold.md) | `min_score=0.02` 形同虚设，无关问题照样返回 ok |
| 003 | [003-evalset.md](003-evalset.md) | 评测集全正例、全 1.00，门禁测不出拒答失效 |
