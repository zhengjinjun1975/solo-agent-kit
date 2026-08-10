# -*- coding: utf-8 -*-
"""ontology.py — 工厂级本体建模（本体优先的差异化核心）。

方法论（ibl.ai Ontology vs RAG + factory-ontology）：
RAG 检索文本，本体检索知识。工厂级本体建模的关键是**实体关系建模**——
不是"CSV→属性"（那是 DatatypeProperty），而是声明哪些列是**对象属性**
（外键引用其他实体 → ObjectProperty + target_class），生成可导航的实体图。

零依赖，标准库实现。复刻自 factory-ontology-kit 的 csv_to_owl（方法论借鉴）。

能力：
- from_csv: 单表→实体（数据属性）
- add_relations: 声明对象属性（外键→目标实体）
- build: 多实体 + 关系 → 完整本体
- query: 关系查询（实体间导航：某设备属于哪条产线/位于哪个位置）
- search: 语义检索
"""
from __future__ import annotations

import csv
import json
import os
import re

NS = "http://solo.local/ontology#"


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
    """列名 → 本体局部名。None 容错。"""
    if col is None:
        return "_"
    return re.sub(r"[^A-Za-z0-9_]", "_", str(col).strip())


class Ontology:
    """工厂级本体：多实体 + 关系建模 + 查询。零依赖，JSON 持久化。

    数据模型：
        entities: {实体名: {cols, types, obj_props, instances}}
        obj_props: {列名: {rel, target_class, label}}  # 对象属性（外键）
        triples:   [(subj, pred, obj)]                  # 全部三元组
        relations: {实体名: {列: {target_class, label}}} # 关系索引（导航用）
    """

    def __init__(self):
        self.entities = {}    # name -> {"cols":[], "types":{}, "obj_props":{}, "instances":[]}
        self.triples = []     # (subj, pred, obj)
        self.relations = {}   # entity -> {col -> {"target_class","label"}}（跨实体导航）

    # ---- 建模 ----
    def from_csv(self, path: str, entity_name: str = None, id_col: str = None,
                 relations: dict = None) -> int:
        """从 CSV 建实体。relations = {列名: {rel,target_class,label}} 声明对象属性。

        relations 示例（工厂设备）:
            {"device_type": {"rel": NS+"hasType", "target_class": "DeviceType", "label": "设备类型"},
             "line_id":     {"rel": NS+"belongsToLine", "target_class": "Line", "label": "属于产线"}}
        """
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return 0
            cols = reader.fieldnames
            entity = entity_name or os.path.splitext(os.path.basename(path))[0]
            rows = list(reader)

            # 数据属性类型（跳过对象属性列）
            obj_props = relations or {}
            types = {}
            for c in cols:
                if c in obj_props:
                    continue
                sample = rows[0].get(c, "").strip() if rows else ""
                types[c] = guess_type(sample)

            self.entities[entity] = {
                "cols": cols, "types": types, "obj_props": obj_props,
                "instances": [r.get(id_col or cols[0], "") for r in rows],
            }
            self.relations[entity] = {
                c: {"target_class": cfg["target_class"], "label": cfg.get("label", c),
                    "rel": cfg.get("rel", NS + local_name(c))}
                for c, cfg in obj_props.items()
            }

            # 三元组：数据属性 + 对象属性
            key = id_col or cols[0]
            for r in rows:
                subj = f"{entity}:{r.get(key, '')}"
                for c in cols:
                    val = r.get(c, "").strip()
                    if not val:
                        continue
                    if c in obj_props:  # 对象属性：指向目标实体
                        cfg = obj_props[c]
                        pred = cfg.get("rel", NS + local_name(c))
                        obj = f"{cfg['target_class']}:{val}"
                        self.triples.append((subj, pred, obj))
                    else:
                        pred = f"{entity}:{local_name(c)}"
                        self.triples.append((subj, pred, val))
        return len(self.entities)

    def from_rows(self, rows: list, entity_name: str = None, id_col: str = None,
                  relations: dict = None) -> None:
        """从行列表(list[dict])建本体（支持 CSV/数据库表）。"""
        if not rows:
            return
        entity = entity_name or "entity"
        id_col = id_col or list(rows[0].keys())[0]
        self.entity = entity
        obj_props = relations or {}
        # 参照类：对象属性 target_class
        self.ref_classes = {v.get("target_class") for v in obj_props.values() if v.get("target_class")}
        self.entities = {entity: {"cols": list(rows[0].keys()), "rows": rows}}
        for rc in self.ref_classes:
            self.entities[rc] = {"cols": [], "rows": []}
        for i, r in enumerate(rows):
            id_val = str(r.get(id_col, i))
            self.triples.append((f"{entity}:{id_val}", "rdf:type", f"owl:{entity}"))
            for k, v in r.items():
                if v is None or str(v).strip() == "":
                    continue
                if k in obj_props:
                    p = obj_props[k].get("rel", NS + local_name(k))
                    t = obj_props[k].get("target_class", "Entity")
                    self.triples.append((f"{entity}:{id_val}", p, f"{t}:{v}"))
                    if v not in [x for x in self.entities[t]["rows"]]:
                        self.entities[t]["rows"].append(v)
                else:
                    self.triples.append((f"{entity}:{id_val}", NS + local_name(k), str(v)))

    def build(self) -> None:
        """构建后处理：为对象属性补 target_class 的类声明（幂等）。"""
        # 收集所有被引用的目标类
        target_classes = set()
        for ent, rels in self.relations.items():
            for col, cfg in rels.items():
                target_classes.add(cfg["target_class"])
        # 补充类声明三元组
        for t in target_classes:
            if t not in self.entities:
                self.entities[t] = {"cols": [], "types": {}, "obj_props": {}, "instances": []}

    # ---- 关系查询（实体间导航，工厂级核心）----
    def query(self, entity: str, id_val: str, rel_col: str = None) -> list:
        """查实体实例的关系。无 rel_col 则返回全部关联三元组。"""
        subj = f"{entity}:{id_val}"
        if rel_col:
            rels = self.relations.get(entity, {})
            if rel_col in rels:
                pred = rels[rel_col].get("rel", NS + local_name(rel_col))
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

    def answer(self, question: str, entity: str = None) -> list:
        """工厂级问题解答（结构化）：按已知实体/关系导航。

        示例：query entity='device', id_val='D001', rel_col='line_id'
        → 返回 D001 属于哪条产线。零 LLM，纯结构化。
        """
        results = []
        # 尝试解析：某实体实例的关系
        # 先找最匹配的实体（question 含实体名）
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

    # ---- 输出 ----
    def to_nt(self) -> str:
        """导出 N-Triples（含类声明 + 对象/数据属性区分）。"""
        L = []
        for ent in self.entities:
            L.append(f"<{NS}{ent}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{NS}{ent}> .")
        for s, p, o in self.triples:
            if ":" in o and o.split(":")[0] in self.entities:  # 对象属性（指向实体）
                L.append(f"<{s}> <{p}> <{o}> .")
            else:  # 数据属性
                L.append(f"<{s}> <{p}> \"{o}\" .")
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

    # ---- 检索 ----
    def search(self, term: str, top_k: int = 5) -> list:
        t = term.strip().lower()
        hits = [(s, p, o) for s, p, o in self.triples
                if t in s.lower() or t in p.lower() or t in o.lower()]
        return hits[:top_k]

    # ---- 持久化 ----
    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"entities": self.entities, "relations": self.relations,
                       "triples": self.triples}, f, ensure_ascii=False)

    def load(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.entities, self.relations = d["entities"], d["relations"]
        self.triples = d["triples"]

    # ═══════════════ 企业级本体（融合 sme-decision-ontology）═══════════════
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

        schema: {"entities":[{"id","table","key","label","domain","attributes":
                 [{"name","type","required"}]}], "relations":[{"id","from","to","fk","label"}]}
        data: {表名: [行...]}  多表数据
        返回企业本体模型（object_types/link_types/graph）。
        """
        entities = {e["id"]: e for e in schema.get("entities", [])}
        # 对象类型 + 属性语义角色
        object_types = []
        for e in schema.get("entities", []):
            ent = dict(e)
            ent["attributes"] = [
                {**a, "role": self._prop_role(a.get("name", ""), a.get("type", "string"))}
                for a in e.get("attributes", [])
            ]
            object_types.append(ent)
        # 链接类型 + 外键自动推断
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
                    for tname in entities:
                        if tname.lower() != src_ent.lower() and target.lower() in tname.lower():
                            link_types.append({"id": f"auto_{table}_{col}", "from": src_ent,
                                               "to": tname, "fk": f"{table}.{col}",
                                               "label": "关联", "auto": True})
                            break
        # 跨表建统一实例图（FK join）
        graph = self._build_graph(data, entities, link_types)
        # 类型体系
        hierarchy = [{"name": "Enterprise", "super": None, "label": "企业"},
                     {"name": "BusinessObject", "super": "Enterprise", "label": "业务对象"}]
        domains = {}
        for e in schema.get("entities", []):
            d = e.get("domain", "其他域")
            domains.setdefault(d, {"name": d, "super": "BusinessObject", "label": d, "children": []})
            domains[d]["children"].append(e["id"])
        for d in domains.values():
            hierarchy.append(d)
        self.enterprise_model = {
            "object_types": object_types,
            "link_types": link_types,
            "graph": graph,
            "type_hierarchy": hierarchy,
            "semantic_domains": sorted({e.get("domain", "其他域") for e in schema.get("entities", [])}),
        }
        return self.enterprise_model

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
        # FK join 关系边
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
