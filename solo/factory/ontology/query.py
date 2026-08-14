# -*- coding: utf-8 -*-
"""query.py — Ontology 关系查询职责：query / neighbors。"""
from __future__ import annotations

# (plain mixin, no _Core inheritance)
from . import _naming  # NS / local_name


class _QueryMixin:
    # ---- 关系查询（实体间导航，工厂级核心）----
    def query(self, entity: str, id_val: str, rel_col: str = None) -> list:
        """查实体实例的关系。无 rel_col 则返回全部关联三元组。"""
        subj = f"{entity}:{id_val}"
        if rel_col:
            rels = self.relations.get(entity, {})
            if rel_col in rels:
                pred = rels[rel_col].get("rel", _naming.NS + _naming.local_name(rel_col))
                return [o for s, p, o in self.triples if s == subj and p == pred]
            # fallback: 按局部名
            return [o for s, p, o in self.triples if s == subj and rel_col in p]
        return [(p, o) for s, p, o in self.triples if s == subj]

    def neighbors(self, entity: str, id_val: str) -> list:
        """返回实体的所有关系邻居（目标实体实例）。"""
        out = []
        for s, p, o in self.triples:
            if s == f"{entity}:{id_val}" and ":" in o:
                out.append(o)
        return out
