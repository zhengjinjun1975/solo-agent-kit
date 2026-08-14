# -*- coding: utf-8 -*-
"""enterprise.py — Ontology 企业级建模职责（融合 sme-decision-ontology）。

from_schema（原圈复杂度 16）按阶段拆成 _build_object_types / _build_link_types /
_build_hierarchy 三个子方法，调度函数只做编排，复杂度显著下降。
"""
from __future__ import annotations

# (plain mixin, no _Core inheritance)


class _EnterpriseMixin:
    # 属性语义角色（Palantir 式）：identifier/reference/measure/category/timestamp/text
    _MEASURE_HINTS = ("qty", "amount", "price", "cost", "stock", "pct", "days",
                      "months", "age", "limit", "rank", "rate", "num", "weight", "size", "power")
    _DATE_HINTS = ("date", "time", "day", "install", "create")
    _CATEGORY_HINTS = ("category", "type", "status", "state", "kind", "flag", "grade", "level")

    def _prop_role(self, col: str, ptype: str) -> str:
        """属性语义角色分类。"""
        low = col.lower()
        if low == "id" or col.endswith("_id"):
            return "identifier"
        if col.endswith("_id") or col.endswith("_code"):
            return "reference"
        if ptype in ("decimal", "integer") or any(h in low for h in self._MEASURE_HINTS):
            return "measure"
        if ptype == "date" or any(h in low for h in self._CATEGORY_HINTS):
            return "category"
        if any(h in low for h in self._DATE_HINTS):
            return "timestamp"
        return "text"

    def from_schema(self, schema: dict, data: dict) -> dict:
        """企业级本体：schema 驱动 + 跨表 join 建统一实例图。

        schema: {"entities":[{...}], "relations":[{...}]}
        data: {表名: [行...]}  多表数据
        返回企业本体模型（object_types/link_types/graph/type_hierarchy/semantic_domains）。
        """
        entities = {e["id"]: e for e in schema.get("entities", [])}
        object_types = self._build_object_types(schema)
        link_types = self._build_link_types(schema, data, entities)
        # 跨表建统一实例图（FK join）
        graph = self._build_graph(data, entities, link_types)
        # 类型体系
        hierarchy = self._build_hierarchy(schema, entities)
        self.enterprise_model = {
            "object_types": object_types,
            "link_types": link_types,
            "graph": graph,
            "type_hierarchy": hierarchy,
            "semantic_domains": sorted({e.get("domain", "其他域") for e in schema.get("entities", [])}),
        }
        return self.enterprise_model

    def _build_object_types(self, schema: dict) -> list:
        """对象类型 + 属性语义角色标注。"""
        object_types = []
        for e in schema.get("entities", []):
            ent = dict(e)
            ent["attributes"] = [
                {**a, "role": self._prop_role(a.get("name", ""), a.get("type", "string"))}
                for a in e.get("attributes", [])
            ]
            object_types.append(ent)
        return object_types

    def _build_link_types(self, schema: dict, data: dict, entities: dict) -> list:
        """链接类型 + 外键自动推断。"""
        link_types = list(schema.get("relations", []))
        declared_fks = {r.get("fk") for r in link_types if r.get("fk")}
        for table, rows in data.items():
            if not rows:
                continue
            # 找该表对应的实体
            src_ent = None
            for eid, e in entities.items():
                if e.get("table") == table:
                    src_ent = eid
                    break
            if not src_ent:
                continue
            for col in rows[0]:
                if col.endswith(("_id", "_code")) and f"{table}.{col}" not in declared_fks:
                    target = col.replace("_id", "").replace("_code", "")
                    # 同义词映射（device↔equipment 等），让外键列能指向语义匹配的实体
                    SYN = {"device": "equipment", "equip": "equipment", "machine": "equipment",
                           "product": "product", "customer": "customer", "supplier": "supplier",
                           "sensor": "sensor", "wo": "workorder", "work": "workorder"}
                    target = SYN.get(target, target)
                    for tname in entities:
                        if tname.lower() != src_ent.lower() and (target.lower() in tname.lower()
                                                                 or tname.lower() in target.lower()):
                            link_types.append({"id": f"auto_{table}_{col}", "from": src_ent,
                                               "to": tname, "fk": f"{table}.{col}",
                                               "label": "关联", "auto": True})
                            break
        return link_types

    def _build_hierarchy(self, schema: dict, entities: dict) -> list:
        """类型体系：Enterprise → BusinessObject → 各语义域。"""
        hierarchy = [{"name": "Enterprise", "super": None, "label": "企业"},
                     {"name": "BusinessObject", "super": "Enterprise", "label": "业务对象"}]
        domains = {}
        for e in schema.get("entities", []):
            d = e.get("domain", "其他域")
            domains.setdefault(d, {"name": d, "super": "BusinessObject", "label": d, "children": []})
            domains[d]["children"].append(e["id"])
        for d in domains.values():
            hierarchy.append(d)
        return hierarchy

    def _build_graph(self, data: dict, entities: dict, relations: list) -> dict:
        """跨表 join 建统一实例图：节点 + 关系边。"""
        graph = {"nodes": {}, "edges": []}
        node_ids = {}
        for eid, ent in entities.items():
            table = ent["table"]
            if table not in data:
                continue
            key = ent["key"]
            for i, row in enumerate(data[table]):
                kid = row.get(key, i)
                node_id = f"{eid}:{kid}"
                graph["nodes"][node_id] = {"entity": eid, "id": kid, "idx": i, "data": row}
                node_ids.setdefault(eid, []).append(node_id)

        # FK join 关系边（去重：同一 from→to→rel 只保留一条，避免 traverse 重复边）
        seen_edges = set()
        for r in relations:
            if not r.get("fk"):
                continue
            ftable, fcol = r["fk"].split(".")
            if ftable not in data:
                continue
            to_e = entities.get(r["to"], {})
            fk_to_nodes = {}
            for nd in node_ids.get(r["to"], []):
                info = graph["nodes"][nd]
                fk_to_nodes.setdefault(str(info["id"]), []).append(nd)
            for row in data[ftable]:
                val = row.get(fcol)
                if not val:
                    continue
                src_key = row.get(entities.get(r["from"], {}).get("key", ""), "")
                src = f"{r['from']}:{src_key}"
                for dst in fk_to_nodes.get(str(val), []):
                    if src in graph["nodes"] and dst in graph["nodes"]:
                        key = (src, dst, r["id"])
                        if key in seen_edges:
                            continue
                        seen_edges.add(key)
                        graph["edges"].append({"from": src, "to": dst, "rel": r["id"],
                                               "label": r.get("label", r["id"])})
        return graph

    def validate(self, schema: dict, data: dict) -> list:
        """约束校验：unique/required/positive。返回问题清单。"""
        issues = []
        entities = {e["id"]: e for e in schema.get("entities", [])}
        for ent in entities.values():
            table, key = ent["table"], ent["key"]
            if table not in data:
                continue
            seen = set()
            for row in data[table]:
                kid = row.get(key)
                if kid in seen:
                    issues.append({"severity": "error", "type": "unique",
                                   "msg": f"实体 {ent['id']} 主键重复: {kid}"})
                seen.add(kid)
                for attr in ent.get("attributes", []):
                    v = row.get(attr.get("name"))
                    if attr.get("required") and (v is None or str(v).strip() == ""):
                        issues.append({"severity": "error", "type": "required",
                                       "msg": f"{ent.get('label', ent['id'])}.{attr.get('label', attr['name'])} 必填缺失"})
        return issues

    def traverse(self, entity: str, eid) -> list:
        """跨域图遍历：从某实体实例出发，返回关联实例。"""
        if not hasattr(self, "enterprise_model"):
            return []
        graph = self.enterprise_model.get("graph", {})
        start = f"{entity}:{eid}"
        if start not in graph.get("nodes", {}):
            return []
        result = []
        for e in graph.get("edges", []):
            if e["from"] == start:
                result.append({"rel": e["rel"], "label": e["label"], "to": e["to"]})
            elif e["to"] == start:
                result.append({"rel": e["rel"], "label": e["label"], "from": e["from"]})
        return result
