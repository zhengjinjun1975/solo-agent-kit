# -*- coding: utf-8 -*-
"""output.py — Ontology 输出职责：to_nt / to_dict / entity_summary。"""
from __future__ import annotations

# (plain mixin, no _Core inheritance)
from . import _naming  # NS


class _OutputMixin:
    # ---- 输出 ----
    def to_nt(self) -> str:
        """导出 N-Triples（对齐 factory-ontology-kit 格式）。

        类声明 rdf:type owl:Class + label；实例三元组用标准 http URI；
        数据属性声明 owl:DatatypeProperty，对象属性（外键引用）声明 owl:ObjectProperty，
        使 solo 建模产出可被 factory 本体问答链路消费。
        """
        OWL = "http://www.w3.org/2002/07/owl#"
        RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        RDFS = "http://www.w3.org/2000/01/rdf-schema#"

        def _inst(u):
            # "实体:ID" / "实体_ID" → NS#实体_ID
            u = str(u)
            if ":" in u:
                e, i = u.split(":", 1)
                return f"{_naming.NS}{e}_{i}"
            return f"{_naming.NS}{u}"

        def _prop(p):
            # NS+local_name / "实体:attr" → NS#local_name
            p = str(p)
            if ":" in p:
                return f"{_naming.NS}{p.split(':', 1)[1]}"
            return p if p.startswith(_naming.NS) else f"{_naming.NS}{p}"

        L = []
        # 1. 类声明 + label
        for ent in self.entities:
            e = f"{_naming.NS}{ent}"
            L.append(f"<{e}> <{RDF}type> <{OWL}Class> .")
            L.append(f"<{e}> <{RDFS}label> \"{ent}\" .")
        # 2. 实例三元组 + 收集属性
        datatype_props, object_props = set(), set()
        for s, p, o in self.triples:
            s_uri = _inst(s)
            p_uri = _prop(p)
            o_str = str(o)
            # 对象属性: 值含 ":" 且前缀是实体(引用其他实例)
            is_obj = ":" in o_str and o_str.split(":", 1)[0] in self.entities
            if is_obj:
                o_uri = _inst(o_str)
                object_props.add(p_uri)
                L.append(f"<{s_uri}> <{p_uri}> <{o_uri}> .")
            else:
                datatype_props.add(p_uri)
                L.append(f"<{s_uri}> <{p_uri}> \"{o_str}\" .")
        # 3. 属性声明
        for p in sorted(datatype_props):
            L.append(f"<{p}> <{RDF}type> <{OWL}DatatypeProperty> .")
        for p in sorted(object_props):
            L.append(f"<{p}> <{RDF}type> <{OWL}ObjectProperty> .")
        return "\n".join(L)

    def to_dict(self) -> dict:
        return {"entities": self.entities, "relations": self.relations,
                "triples": self.triples}

    def entity_summary(self) -> str:
        parts = []
        for name, meta in self.entities.items():
            cols = ", ".join(meta["cols"]) if meta["cols"] else "(参照类)"
            rels = ", ".join(f"{c}→{v['target_class']}" for c, v in self.relations.get(name, {}).items())
            line = f"{name}({cols})"
            if rels:
                line += f" 关系[{rels}]"
            parts.append(line)
        return "\n".join(parts)
