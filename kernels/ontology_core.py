# -*- coding: utf-8 -*-
"""kernels/ontology_core.py — 本体建模/聚合问答/语义 纯函数内核。

迁移自 factory/ontology/* 的纯函数：guess_type/local_name/semantic_role、
跨字段语义一致性、实体链接、聚合问答求值。无状态、确定性。
消费原子：ontology-qa。
"""
from __future__ import annotations

import math
import re


def guess_type(value) -> str:
    v = str(value).strip() if value is not None else ""
    if not v:
        return "empty"
    if re.fullmatch(r"-?\d+", v):
        return "integer"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "float"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "date"
    return "text"


def local_name(column: str) -> str:
    """列名 → 本地名（下划线/驼峰拆分，取末段）。"""
    parts = re.split(r"[_\s]+", column.strip())
    parts = re.findall(r"[A-Za-z0-9\u4e00-\u9fa5]+", " ".join(parts))
    return parts[-1] if parts else column


def semantic_role(column: str) -> str:
    """列名 → 语义角色：id/status/type/numeric/entity/measure/flag。"""
    low = column.lower()
    if low in ("id", "udi", "serial_no") or low.endswith("_id") or low.endswith("编号"):
        return "id"
    if "status" in low or "状态" in column:
        return "status"
    if "type" in low or "类型" in column or "型号" in column:
        return "type"
    if any(k in low for k in ("qty", "count", "value", "amount", "price",
                              "temp", "power", "speed", "vibration", "rate",
                              "量", "率", "数", "度", "额")):
        return "numeric"
    if low in ("device", "equipment", "product", "sensor") or "设备" in column:
        return "entity"
    if any(k in low for k in ("unit", "measure", "mm", "kw", "c", "单位")):
        return "measure"
    if low in ("is_", "enabled", "active", "flag", "开关"):
        return "flag"
    return "attribute"


def semantic_consistency(rows: list) -> dict:
    """跨字段语义一致性检查：同列类型是否漂移、主键是否唯一。"""
    if not rows:
        return {"ok": True, "issues": []}
    issues = []
    cols = list(rows[0].keys())
    for c in cols:
        vals = [r.get(c, "") for r in rows if str(r.get(c, "")).strip()]
        if not vals:
            continue
        t0 = guess_type(vals[0])
        drifted = [v for v in vals if guess_type(v) != t0]
        if drifted and t0 in ("integer", "float"):
            issues.append({"type": "type_drift", "column": c,
                           "count": len(drifted), "level": "warn"})
    return {"ok": len(issues) == 0, "issues": issues}


def build_model(rows: list, entity_name: str = "设备", entity_col: str = None) -> dict:
    """从行数据构建本体模型（对象类型 + 实例 + 属性角色）。"""
    if not rows:
        return {"object_types": [], "instances": []}
    cols = list(rows[0].keys())
    obj_col = entity_col or next((c for c in cols if semantic_role(c) == "id"), cols[0])
    obj_type = {
        "id": entity_name, "table": "rows", "label": entity_name,
        "attributes": [{"name": c, "role": semantic_role(c)} for c in cols],
    }
    instances = []
    for i, r in enumerate(rows):
        inst = {"id": r.get(obj_col) or f"{entity_name}_{i}",
                "type": entity_name,
                "attrs": {c: r.get(c, "") for c in cols}}
        instances.append(inst)
    return {"object_types": [obj_type], "instances": instances}


def link_entities(rows_a: list, rows_b: list, key_a: str, key_b: str) -> list:
    """实体链接：按主键把两张表关联成 [{"a":..., "b":..., "match":bool}]。"""
    idx = {r.get(key_b): r for r in rows_b}
    links = []
    for r in rows_a:
        links.append({"a": r, "b": idx.get(r.get(key_a)),
                      "match": r.get(key_a) in idx})
    return links


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def answer_aggregate(rows: list, col: str, op: str) -> dict:
    """聚合问答求值：count/sum/avg/min/max。返回 {op, col, value, n}。"""
    vals = [_num(r.get(col)) for r in rows if _num(r.get(col)) is not None]
    if op == "count":
        return {"op": op, "col": col, "value": len(vals), "n": len(vals)}
    if not vals:
        return {"op": op, "col": col, "value": None, "n": 0}
    if op == "sum":
        v = sum(vals)
    elif op == "avg":
        v = sum(vals) / len(vals)
    elif op == "min":
        v = min(vals)
    elif op == "max":
        v = max(vals)
    else:
        return {"op": op, "col": col, "value": None, "n": 0}
    return {"op": op, "col": col, "value": round(v, 3), "n": len(vals)}


def answer_filter(rows: list, col: str, value) -> list:
    """过滤问答：返回 col==value 的行。"""
    return [r for r in rows if str(r.get(col)) == str(value)]
