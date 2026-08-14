# -*- coding: utf-8 -*-
"""core.py — Ontology 状态底座（entities/triples/relations/col_cn）。

仅持有数据 + 构造逻辑，建模/查询/问答/输出等职责拆到各自 mixin。
"""
from __future__ import annotations


class _Core:
    """本体状态容器。entities/triples/relations 为跨职责共享的单一事实来源。"""

    def __init__(self, col_cn: dict = None):
        self.entities = {}    # name -> {"cols":[], "types":{}, "obj_props":{}, "instances":[]}
        self.triples = []     # (subj, pred, obj)
        self.relations = {}   # entity -> {col -> {"target_class","label"}}（跨实体导航）
        # 行业列名中文映射（可选）：供聚合问答 _cn2col 用，与 draft_questions 行业措辞一致。
        # 从 industry 配置联动（改行业即联动问答能答的列名），全局 COL_CN_MAP 为兜底。
        self.col_cn = dict(col_cn or {})
