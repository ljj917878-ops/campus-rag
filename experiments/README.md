# experiments/ — 可复现的实验脚本

这个目录里的脚本都是**只读**的：不改项目代码、不写 `eval_results.json`，只打印结果。
目的很简单：站点上每一个数字，你都应该能在自己机器上跑出来。

前提：用项目自带的 venv（全局 Python 3.13 没装 sklearn）。

在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe experiments\<脚本名>.py
```

## chunk_size_sweep.py

只改切块大小（120 / 180 / 280 / 420），跑同一套 15 题，看「正例 top1 均值」「正例最低」「负例 top1」「关键词是否进 top4」。

```powershell
.\.venv\Scripts\python.exe experiments\chunk_size_sweep.py
```

它回答的问题：切块大小是不是召回瓶颈？
当前答案：不是——四档召回都是 15/15，反而块越小正负例分数一起涨。

## negative_probe.py

拿 20 个「手册里没有」的问题去打检索，看最高分能飙到多高。

```powershell
.\.venv\Scripts\python.exe experiments\negative_probe.py
```

它回答的问题：阈值该定多少？
当前答案：**单看分数定不出来**（负例最高 0.2014 > 正例最低 0.1852，区间重叠），得看 top1 与 top2 的分差。

## threshold_scan.py

把「阈值该定多少」算成一张表：阈值从 0.01 扫到 0.30，列出正例通过率、负例拒答率、均衡准确率；最后单独看「top1−top2 分差」能不能分开正负例。

负例用的是 **34 条合并集**（本仓库 20 条 + 外部评审给的 15 条，去重），每条都核对过手册里确实没有对应条款。

```powershell
.\.venv\Scripts\python.exe experiments\threshold_scan.py
```

它回答的问题：绝对分数够不够用？
当前答案：不够稳——绝对分数最优 0.18，仍漏 1 个负例（0.2014）；而分差 ≥ 0.13 能把 34 个负例全拒、15 个正例全过。

## heldout_check.py

留出测试：12 条**换了问法**的正例 + 11 条「话题在手册里、但这件事没写」的难负例，检查「门槛」和「分差」两条规则在没参与调参的问题上还成不成立。

```powershell
.\.venv\Scripts\python.exe experiments\heldout_check.py
```

它回答的问题：那条分差线是真的，还是过拟合？
当前答案（2026-11-14 实跑）：**过拟合了**。分差 ≥ 0.13 在训练样本上全分开，但留出集上正例只放行 6/12（误拒一半），难负例拒 8/11。而 0.02 门槛反过来：正例 12/12 全放行，难负例只拒 3/11。

结论：单靠一个分数阈值判「有没有依据」不成立，得组合信号。

## 已知局限（别拿这些结论去吹）

- 正例只有 15 条、负例 20 条，样本很小，任何「最优阈值」都只是初步估计
- 忠实度指标（`evaluation.py:174`）对抽取式答案恒为 1.00，没有区分度
- 负例是本文件里手写的，覆盖面有限；真要严谨得多来源采样

## signal_auc.py / signal_auc_claude.py

两份独立实现的「信号体检」：对每个问题算 top1、分差、IDF 加权覆盖率、命中实词数，再用 AUC 看每个信号能不能分开正例和负例。不选阈值，所以不会因为凑阈值虚高。

```powershell
# 自带脚本（正例 12 / 难负例 11 / 离题 20）
.\.venv\Scripts\python.exe experiments\signal_auc.py

# 外部评审版（判定只用检索正确的正例；离题清单单独传）
cd experiments; $env:PYTHONPATH=".."; ..\.venv\Scripts\python.exe signal_auc_claude.py --easy-neg easy_negatives.txt
```

2026-11-14 结果（两版一致，差值在实现细节）：

| 信号 | 对难负例（话题内缺失） | 对离题负例 |
| --- | --- | --- |
| 命中实词数 | 0.87 | 0.88 |
| 覆盖率 | 0.85 | 0.95 |
| top1 | 0.77 | 0.91 |
| 分差 | 0.76 | 0.94 |

同一套代码，训练正例对离题负例的分差 AUC = 1.00。**0.76 / 0.94 / 1.00 取决于拿谁去算**——这就是过拟合陷阱。


## 页面引用的行号怎么保持同步

docs/index.html 里的行号不要手写维护，跑一次工具即可：

`powershell
.\.venv\Scripts\python.exe toolsefresh_refs.py        # 同步
.\.venv\Scripts\python.exe toolsefresh_refs.py --check # 只报告差异，可放进提交前检查
`

它做三件事：

1. <code data-fn="函数名"> 的引用按 def 所在行重算；
2. <code data-snippet="某行代码片段"> 的引用按「包含这段文字的第一行」重算；
3. 四个源文件的行数（data-lines）按真实行数重算，docs/code.html 里每个代码块的 行号范围 按逐行匹配重新定位。

改完 .py 之后跑一遍，页面就不会再和代码对不上。
