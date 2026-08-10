# -*- coding: utf-8 -*-
"""ontology.py — 本体建模（本体优先的差异化核心）。

方法论（ibl.ai Ontology vs RAG）：RAG 检索文本，本体检索知识。
solo 先建"实体-关系-属性"语义结构，再检索——这是区别于普通记忆库的核心。

零依赖：CSV 数据 → 实体-关系-属性三元组（N-Triples 风格），可导出。
复刻自 factory-ontology-kit 的 csv_to_owl（方法论借鉴，标准库实现）。
"""
from __future__ import annotations

import csv
import json
import os
import re


def guess_type(value: str) -> str:
    """启发式猜列类型：整数/浮点/日期/文本。"""
    v = value.strip()
    if re.fullmatch(r"-?\d+", v):
        return "integer"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "decimal"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "date"
    return "string"


def local_name(col: str) -> str:
    """列名 → 本体局部名（下划线保留，去空格/特殊字符）。"""
    return re.sub(r"[^A-Za-z0-9_]", "_", col.strip())


class Ontology:
    """CSV → 实体-关系-属性 本体。语义锚点，供 memory/agent 检索用。"""

    def __init__(self):
        self.entities = {}   # entity_name -> {"cols": [...], "types": {...}}
        self.triples = []    # list of (subj, pred, obj)

    def from_csv(self, path: str, entity_name: str = None, id_col: str = None) -> int:
        """从 CSV 建本体。返回实体数。entity_name 默认文件名；id_col 指定主键列。"""
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0
            cols = reader.fieldnames
            entity = entity_name or os.path.splitext(os.path.basename(path))[0]
            # 类型推断（首行）
            rows = list(reader)
            types = {}
            for c in cols:
                sample = rows[0].get(c, "").strip() if rows else ""
                types[c] = guess_type(sample)
            self.entities[entity] = {"cols": cols, "types": types}
            # 主键：指定 id_col 或第一列
            key = id_col or cols[0]
            for r in rows:
                subj = f"{entity}:{r.get(key, '')}"
                for c in cols:
                    val = r.get(c, "").strip()
                    if val:
                        self.triples.append((subj, f"{entity}:{local_name(c)}", val))
        return len(self.entities)

    def to_nt(self) -> str:
        """导出 N-Triples 格式（可写文件/导入图数据库）。"""
        return "\n".join(f"<{s}> <{p}> \"{o}\" ." for s, p, o in self.triples)

    def to_dict(self) -> dict:
        return {"entities": self.entities, "triples": self.triples}

    def search(self, term: str, top_k: int = 5) -> list:
        """本体语义检索：命中实体名/属性名/值，返回三元组。"""
        t = term.strip().lower()
        hits = [(s, p, o) for s, p, o in self.triples
                if t in s.lower() or t in p.lower() or t in o.lower()]
        return hits[:top_k]

    def entity_summary(self) -> str:
        """本体摘要（agent 上下文用）。"""
        parts = []
        for name, meta in self.entities.items():
            cols = ", ".join(meta["cols"])
            parts.append(f"{name}({cols})")
        return "\n".join(parts)

    # ---- 持久化（零依赖 JSON）----
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"entities": self.entities, "triples": self.triples}, f, ensure_ascii=False)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.entities = d["entities"]
        self.triples = d["triples"]
