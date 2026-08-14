# -*- coding: utf-8 -*-
"""build.py — Ontology 建模职责：from_csv / from_rows / build。"""
from __future__ import annotations

import csv
import os

# (plain mixin, no _Core inheritance)
from . import _naming  # NS / local_name / guess_type


class _BuildMixin:
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
                types[c] = _naming.guess_type(sample)

            self.entities[entity] = {
                "cols": cols, "types": types, "obj_props": obj_props,
                "instances": [r.get(id_col or cols[0], "") for r in rows],
            }
            self.relations[entity] = {
                c: {"target_class": cfg["target_class"], "label": cfg.get("label", c),
                    "rel": cfg.get("rel", _naming.NS + _naming.local_name(c))}
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
                        pred = cfg.get("rel", _naming.NS + _naming.local_name(c))
                        obj = f"{cfg['target_class']}:{val}"
                        self.triples.append((subj, pred, obj))
                    else:
                        pred = f"{entity}:{_naming.local_name(c)}"
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
                    p = obj_props[k].get("rel", _naming.NS + _naming.local_name(k))
                    t = obj_props[k].get("target_class", "Entity")
                    self.triples.append((f"{entity}:{id_val}", p, f"{t}:{v}"))
                    if v not in [x for x in self.entities[t]["rows"]]:
                        self.entities[t]["rows"].append(v)
                else:
                    self.triples.append((f"{entity}:{id_val}", _naming.NS + _naming.local_name(k), str(v)))

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
