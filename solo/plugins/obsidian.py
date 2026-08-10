# -*- coding: utf-8 -*-
"""obsidian.py — Obsidian 知识库集成（零依赖，文件系统读写 vault）。

FDE 现场产出的报告/方案/经验自动归档到 Obsidian 知识库。
Obsidian 笔记应用无官方 CLI，直接用文件系统读写 vault（D:/knowledge-base/obsidian-vault/），
遵循 vault 目录结构（reports/projects/knowledge）+ Markdown 语法（frontmatter/link/tag）。

能力：
  save_report  现场报告/方案归档到 reports/
  search       知识检索（文件名 + 正文关键词）
  save_experience  经验沉淀到 knowledge/
"""
from __future__ import annotations

import os
import re
from datetime import datetime

# vault 根目录（可用环境变量覆盖）
DEFAULT_VAULT = os.environ.get("SOLO_VAULT", r"D:/knowledge-base/obsidian-vault")


def _vault() -> str:
    if not os.path.isdir(DEFAULT_VAULT):
        raise RuntimeError(f"Obsidian vault 不存在: {DEFAULT_VAULT}")
    return DEFAULT_VAULT


def _ensure_dir(rel: str) -> str:
    d = os.path.join(_vault(), rel)
    os.makedirs(d, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    """文件名清理：去掉非法字符，空格转下划线。"""
    name = re.sub(r'[\\/:*?"<>|]', "_", name.strip())
    return name or "untitled"


def _frontmatter(tags: list = None, **extra) -> str:
    """生成 Markdown frontmatter。"""
    lines = ["---", f"created: {datetime.now().strftime('%Y-%m-%d')}"]
    if tags:
        lines.append("tags: [" + ", ".join(tags) + "]")
    for k, v in extra.items():
        if v is not None:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def save_report(title: str, content: str, tags: list = None,
                category: str = "site") -> dict:
    """现场报告/方案归档到 vault 的 reports/<category>/。

    title: 报告标题（作为文件名）
    content: Markdown 正文
    tags: 标签列表
    category: 归档子目录（site 厂区 / factory 工厂 / analysis 分析）
    """
    safe = _safe_filename(title)
    rel = os.path.join("reports", category)
    d = _ensure_dir(rel)
    path = os.path.join(d, safe + ".md")
    md = _frontmatter(tags=tags, title=title) + "\n\n" + content.strip()
    # 若文件存在则追加时间戳避免覆盖
    if os.path.exists(path):
        path = os.path.join(d, safe + f"_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return {"ok": True, "path": path.replace("\\", "/"),
            "title": title, "category": category}


def search(query: str, scope: str = None, limit: int = 10) -> list:
    """知识检索：按文件名 + 正文关键词（零依赖，文件扫描）。

    query: 关键词
    scope: 限定子目录（如 reports / projects / knowledge），None 全库
    limit: 返回条数
    """
    root = _vault()
    scope_dir = os.path.join(root, scope) if scope else root
    if not os.path.isdir(scope_dir):
        return []
    results = []
    q = query.lower()
    for dp, dirs, files in os.walk(scope_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dp, fn)
            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            # 文件名匹配 or 正文匹配
            score = 0
            if q in fn.lower():
                score += 3
            for line in content.splitlines():
                if q in line.lower():
                    score += 1
            if score:
                results.append({
                    "path": path.replace("\\", "/").replace(root.replace("\\", "/") + "/", ""),
                    "file": fn, "score": score,
                    "snippet": next((l.strip()[:80] for l in content.splitlines()
                                     if q in l.lower()), ""),
                })
    results.sort(key=lambda x: -x["score"])
    return results[:limit]


def save_experience(title: str, content: str, tags: list = None,
                    domain: str = "code") -> dict:
    """现场经验沉淀到 vault 的 knowledge/<domain>/atoms/。

    经验原子化：一个标题一条可复用经验。
    """
    safe = _safe_filename(title)
    rel = os.path.join("knowledge", domain, "atoms")
    d = _ensure_dir(rel)
    path = os.path.join(d, safe + ".md")
    md = (_frontmatter(tags=tags or ["atom"], title=title, type="atom")
          + "\n\n" + content.strip())
    if os.path.exists(path):
        path = os.path.join(d, safe + f"_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return {"ok": True, "path": path.replace("\\", "/"), "title": title,
            "domain": domain}
