# -*- coding: utf-8 -*-
"""页面引用自动对齐：给 docs/ 里带 data-fn / data-lines 的标记重新算行号，
并把 code.html 里每个代码块的行号范围按源码重新定位。

用法（在仓库根）：
    ./.venv/Scripts/python.exe tools/refresh_refs.py [--check]

--check 只报告差异，不写文件（提交前可以当校验用）。
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SOURCES = ["rag_engine.py", "app.py", "generator.py", "evaluation.py"]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def source_lines() -> dict[str, list[str]]:
    return {name: read(ROOT / name).splitlines() for name in SOURCES}


def def_lines(lines: dict[str, list[str]]) -> dict[str, int]:
    """函数/类名 → 定义所在行号（同名取第一次出现）。"""
    out: dict[str, int] = {}
    pat = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)")
    for name, body in lines.items():
        for i, ln in enumerate(body, start=1):
            m = pat.match(ln)
            if m and m.group(1) not in out:
                out[m.group(1)] = i
    return out


def update_index(text: str, defs: dict[str, int], lines: dict[str, list[str]], check: bool) -> tuple[str, list[str]]:
    notes: list[str] = []

    # 1) <code data-fn="xxx">…:NNN</code> → 行号按定义位置重算
    def fix_code(m: re.Match) -> str:
        fn = m.group(1)
        whole = m.group(0)
        if fn not in defs:
            notes.append(f"未知函数 {fn}")
            return whole
        want = defs[fn]
        body = m.group(2)
        new_body = re.sub(r"(?<=:)\d+", str(want), body, count=1)
        if new_body != body:
            notes.append(f"{fn}: {body} → {new_body}")
        return whole.replace(body, new_body, 1)

    text = re.sub(r'<code data-fn="([\w]+)">([^<]*)</code>', fix_code, text)

    # 1b) <code data-snippet="段落标记代码">…:NNN</code> → 按「包含这段文字的第一行」定位
    def fix_snippet(m: re.Match) -> str:
        needle = m.group(1)
        whole = m.group(0)
        body = m.group(2)
        for name in SOURCES:
            for i, ln in enumerate(lines[name], start=1):
                if needle in ln:
                    new_body = re.sub(r"(?<=:)\d+", str(i), body, count=1)
                    if new_body != body:
                        notes.append(f"[{name}] {body} → {new_body}（{needle[:20]}）")
                    return whole.replace(body, new_body, 1)
        notes.append(f"未找到代码行：{needle[:30]}")
        return whole

    text = re.sub(r'<code data-snippet="([^"]+)">([^<]*)</code>', fix_snippet, text)

    # 2) <span data-lines="app.py">209</span> → 文件实际行数
    def fix_lines(m: re.Match) -> str:
        fname = m.group(1)
        whole = m.group(0)
        if fname not in lines:
            notes.append(f"未知文件 {fname}")
            return whole
        want = len(lines[fname])
        body = m.group(2)
        if body.strip() != str(want):
            notes.append(f"{fname} 行数: {body} → {want}")
        return whole.replace(f">{body}<", f">{want}<", 1)

    text = re.sub(r'<span data-lines="([\w.]+)">(\d+)</span>', fix_lines, text)
    return text, notes


def locate(lines: list[str], block: list[str]) -> int | None:
    """在源码里找这段代码的起始行（逐行去缩进后比较）。"""
    stripped_src = [ln.strip() for ln in lines]
    n = len(block)
    target = [ln.strip() for ln in block]
    for i in range(len(stripped_src) - n + 1):
        if stripped_src[i : i + n] == target:
            return i + 1
    return None


def update_code(text: str, lines: dict[str, list[str]], check: bool) -> tuple[str, list[str]]:
    notes: list[str] = []
    pat = re.compile(
        r'<div class="ln">([\d–\-]+)</div><pre>(.*?)</pre>',
        re.S,
    )

    def fix(m: re.Match) -> str:
        old_range, raw = m.group(1), m.group(2)
        code = html.unescape(raw)
        block = code.splitlines()
        while block and not block[-1].strip():
            block.pop()
        while block and not block[0].strip():
            block.pop(0)
        if not block:
            return m.group(0)
        for name in SOURCES:
            start = locate(lines[name], block)
            if start is not None:
                end = start + len(block) - 1
                want = f"{start}" if start == end else f"{start}–{end}"
                if want != old_range:
                    notes.append(f"[{name}] {old_range} → {want}")
                    return m.group(0).replace(f'<div class="ln">{old_range}</div>', f'<div class="ln">{want}</div>', 1)
                return m.group(0)
        notes.append(f"未找到代码块（原 {old_range}）：{block[0][:40]}")
        return m.group(0)

    text = pat.sub(fix, text)
    return text, notes


def main() -> int:
    check = "--check" in sys.argv
    lines = source_lines()
    defs = def_lines(lines)
    changed = 0

    idx = DOCS / "index.html"
    t = read(idx)
    t2, notes = update_index(t, defs, lines, check)
    for n in notes:
        print("index:", n)
    if t2 != t and not check:
        idx.write_text(t2, encoding="utf-8")
        changed += 1

    code = DOCS / "code.html"
    c = read(code)
    c2, notes = update_code(c, lines, check)
    for n in notes:
        print("code:", n)
    if c2 != c and not check:
        code.write_text(c2, encoding="utf-8")
        changed += 1

    print(f"{'需更新' if check else '已更新'} {changed} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
