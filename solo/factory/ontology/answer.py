# -*- coding: utf-8 -*-
"""answer.py — Ontology 问答职责：关系导航 + 聚合问答（计数/极值/枚举/列表）。

聚合问答原为单函数 _answer_aggregate（圈复杂度 20），按题型拆成 4 个独立方法
（_agg_count / _agg_extreme / _agg_enum / _agg_list），每个分支一个方法，
调度函数只做"匹配→分派"，圈复杂度降至 ~5。
"""
from __future__ import annotations

import re

# (plain mixin, no _Core inheritance)
from . import _naming  # guess_type


class _AnswerMixin:
    def answer(self, question: str, entity: str = None) -> list:
        """工厂级问题解答（结构化）：关系导航 + 聚合问答。

        支持两类：
        1. 聚合问答（闭环 draft_questions 生成题可答，零 LLM）：
             - 计数  有多少台设备 / 有多少个阀门
             - 极值  功率最大的设备 / 公称通径最小的阀门
             - 枚举  设备类型有哪些 / 状态有哪些 / 区域有哪些
             - 列表  有哪些设备（取名称列去重）
        2. 关系导航（原能力）：某设备属于哪条产线 / 位于哪个位置
          （query entity, id_val, rel_col）

        示例：query entity='device', id_val='D001', rel_col='line_id'
        → 返回 D001 属于哪条产线。纯结构化，无 LLM。
        """
        q = str(question).strip()
        # 聚合问答优先（修闭环断裂：draft_questions 生成题在此可答）
        agg = self._answer_aggregate(q, entity)
        if agg is not None:
            return agg
        # 关系导航（原能力）
        results = []
        for ent, rels in self.relations.items():
            if entity is None or ent == entity:
                for col, cfg in rels.items():
                    if cfg["label"] in question:
                        # 找该实体的所有实例，查这个关系
                        for inst in self.entities.get(ent, {}).get("instances", [])[:10]:
                            val = self.query(ent, inst, col)
                            if val:
                                results.append({"entity": ent, "instance": inst,
                                                "rel": cfg["label"], "value": val[0]})
        return results

    @staticmethod
    def _is_num(v) -> bool:
        """是否数值（聚合极值用）。"""
        return _naming.guess_type(str(v).strip()) in ("integer", "decimal")

    @staticmethod
    def _is_name_col(col: str) -> bool:
        """是否名称类列（列表问答取名称列用）。"""
        low = str(col).strip().lower()
        return any(k in low for k in ("名称", "名字", "name"))

    def _cn2col(self, headers) -> dict:
        """列名 → 中文 反查表（复用 assist 词典映射，与 draft_questions 措辞一致）。

        先查行业 col_cn（Ontology 构造时注入的行业配置，改行业即联动），
        再回退 assist 全局 COL_CN_MAP 兜底，保证行业化列名（如 阀门类型→valve_type）可答。
        """
        try:
            from ..assist import _col_cn_for  # noqa: PLC0415  # 惰性导入避免循环依赖
            return {_col_cn_for(c, self.col_cn): c for c in headers}
        except Exception:  # noqa: BLE001
            return {}

    def _answer_aggregate(self, q: str, entity=None):
        """聚合问答：计数/极值/枚举/列表。无法匹配 → 返回 None（交回关系导航）。"""
        rows_ents = [e for e, m in self.entities.items() if m.get("rows")]
        if not rows_ents:
            return None
        ent, rows, cn2col = self._agg_context(q, entity, rows_ents)
        if not rows:
            return None

        # 1) 计数：有多少[量词][实体]
        m = re.match(r"^有多少[个台条位家本批艘]?(.+)$", q)
        if m:
            res = self._agg_count(m.group(1).strip(), ent, rows_ents, q)
            if res is not None:
                return res

        # 2) 极值：功率最大的设备 / 价格最高的设备 / 数量最多的产品 / 重量最轻的零件 ...
        #    扩展极值词（最大/最高/最贵/最多/最小/最低/最便宜/最少等），非仅 大|小
        m = re.match(r"^(?P<col>.+?)最(?P<ext>高|低|贵|便宜|多|少|大|小)的(?P<ent>.*)$", q)
        if m:
            res = self._agg_extreme(m, ent, rows, cn2col, q)
            if res is not None:
                return res

        # 3) 枚举：[列名]有哪些
        m = re.match(r"^(?P<col>.+?)有哪些$", q)
        if m:
            res = self._agg_enum(m.group("col"), ent, rows, cn2col, q)
            if res is not None:
                return res

        # 4) 列表：有哪些[实体]（取名称列去重）
        m = re.match(r"^有哪些(.+)$", q)
        if m:
            res = self._agg_list(m.group(1).strip(), ent, rows, rows_ents, q)
            if res is not None:
                return res
        return None

    def _agg_context(self, q, entity, rows_ents):
        """确定聚合问答的目标实体 + 行集 + 列名反查表。"""
        # entity 参数优先；否则按题面含实体名；再默认第一个主实体
        ent = None
        if entity and entity in self.entities and self.entities[entity].get("rows"):
            ent = entity
        else:
            ent = next((e for e in rows_ents if e in q), None) or rows_ents[0]
        rows = self.entities[ent].get("rows", [])
        headers = list(rows[0].keys()) if rows else []
        cn2col = self._cn2col(headers) if headers else {}
        return ent, rows, cn2col

    def _target_col(self, cn2col, colcn):
        """列中文/英文 → 实际列名。"""
        return cn2col.get(colcn.strip(), colcn.strip())

    def _agg_count(self, subj, ent, rows_ents, q):
        """计数题：有多少台设备 / 有多少个阀门。"""
        if not subj or subj == ent or subj in rows_ents:
            return [{"type": "count", "entity": ent, "question": q, "value": len(self.entities[ent]["rows"])}]
        return None

    def _agg_extreme(self, m, ent, rows, cn2col, q):
        """极值题：[列名]最大的[实体] / 最小的[实体]。"""
        col = self._target_col(cn2col, m.group("col"))
        scored = [(float(r[col]), r) for r in rows
                  if r.get(col) is not None and str(r[col]).strip() != "" and self._is_num(r[col])]
        if not scored:
            return None
        is_max = m.group("ext") in ("大", "高", "贵", "多")
        extreme = "最" + m.group("ext")
        _, best = (max if is_max else min)(scored, key=lambda x: x[0])
        return [{"type": "extreme",
                 "extreme": extreme,
                 "entity": ent,
                 "column": col,
                 "column_cn": m.group("col").strip(),
                 "value": best.get(col), "instance": best, "question": q}]

    def _agg_enum(self, colcn, ent, rows, cn2col, q):
        """枚举题：[列名]有哪些。"""
        col = self._target_col(cn2col, colcn)
        uniq = sorted({str(r[col]).strip() for r in rows
                       if r.get(col) is not None and str(r[col]).strip()})
        if not uniq:
            return None
        return [{"type": "enum", "entity": ent, "column": col,
                 "column_cn": colcn.strip(),
                 "values": uniq, "question": q}]

    def _agg_list(self, subj, ent, rows, rows_ents, q):
        """列表题：有哪些[实体]（取名称列去重）。"""
        if not subj or subj == ent or subj in rows_ents:
            headers = list(rows[0].keys()) if rows else []
            name_col = next((c for c in headers if self._is_name_col(c)), None)
            if not name_col:
                # 无名称列：回退 id 列（id / *_id），保证"有哪些X"可答不落空
                name_col = next((c for c in headers
                                 if c.strip().lower() == "id" or c.lower().endswith("_id")), None)
            if name_col:
                names = sorted({str(r[name_col]).strip() for r in rows
                                if r.get(name_col) is not None and str(r[name_col]).strip()})
                return [{"type": "list", "entity": ent, "column": name_col,
                         "values": names, "question": q}]
        return None
