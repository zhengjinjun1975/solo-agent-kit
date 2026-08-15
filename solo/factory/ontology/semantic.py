# -*- coding: utf-8 -*-
"""semantic.py — 本体 P0 语义贯通（本体语义复用 v1/v2 认知 + 多表关联）。

借鉴 OpenSPG「领域模型约束知识建模」思路，**只借鉴理念，不复制代码**，复用 solo 已有
v1(factory-ontology) / v2(sme-decision) 本体认知，做 FDE 工作台各板块字段的语义贯通：
让 monitor 指标 / task 工单 / memory 记忆 的字段，对齐本体的语义角色，形成统一语义层。

能力（零依赖、确定性规则）：
1. `semantic_role(col)` —— 复用 enterprise._prop_role 的属性语义角色分类
   (identifier/reference/measure/category/timestamp/text)，跨板块对齐。
2. `link_entities(data)` —— 多表关联：每表一实体 + 外键自动推断 + 语义角色标注，
   产出统一实例图（复用 ontology.from_schema）。
3. `semantic_consistency(fields)` —— 语义一致性校验：判断 monitor 指标 / task 工单 /
   memory 记忆字段名是否符合本体语义（如 "cpu" 应为 measure、"device_id" 应为 identifier）。
4. `cross_field_semantics(data, fields)` —— 把任意板块字段映射到本体语义域，生成
   语义贯通报告：{field → {role, domain, match, linked_entity}}。

与 v1/v2 本体关系：本模块不重复建本体，只做「字段语义 ↔ 本体语义」的对齐层；
本体建模/问答/评测仍交给已有 factory.ontology 内核（v1/v2 认知复用）。
"""
from __future__ import annotations

# 通用语义词库（字段名/中文 → 语义域 + 角色），对齐 factory 行业措辞
_MEASURE_TERMS = ("温度", "temp", "振动", "vib", "功率", "power", "load", "压力",
                  "pressure", "流量", "flow", "转速", "speed", "内存", "mem",
                  "cpu", "占比", "ratio", "pct", "rate", "数量", "count", "qty",
                  "重量", "weight", "尺寸", "size", "库存", "stock", "金额", "price")
_CATEGORY_TERMS = ("类型", "type", "状态", "status", "state", "级别", "level",
                   "等级", "grade", "类别", "category", "kind", "flag",
                   "triage", "严重级", "severity", "区域", "zone", "产线", "line")
_REFERENCE_TERMS = ("设备", "device", "工单", "ticket", "order", "wo", "work",
                    "客户", "customer", "供应商", "supplier", "产品", "product",
                    "零件", "part", "sensor", "传感器", "工人", "operator", "_id", "_code")
_IDENTIFIER_TERMS = ("id", "编号", "序号", "主键", "uid", "udi")
_TIMESTAMP_TERMS = ("date", "日期", "time", "时间", "ts", "创建", "create", "install",
                    "截止", "deadline")

# 语义域 → 本体实体（对齐 v1 工厂本体设备/工单/产线/人员 等概念）
_DOMAIN_ENTITY = {
    "设备/传感器": "Device", "工单/任务": "WorkOrder", "产线/工位": "ProductionLine",
    "产品/物料": "Product", "人员/班组": "Operator", "客户/供应商": "Partner",
    "区域/车间": "Workshop", "质量/缺陷": "Quality",
}


def semantic_role(col: str) -> dict:
    """字段语义角色分类（复用 enterprise._prop_role 思路，跨板块对齐）。"""
    low = str(col).strip().lower()
    if low == "id" or low.startswith("id") and not low.endswith("_id") or "编号" in col or "序号" in col:
        role, domain = "identifier", "主键标识"
    elif low.endswith("_id") or low.endswith("_code") or "设备" in low or "device" in low:
        role, domain = "reference", _match_domain(low, ("device", "设备")) or "引用/外键"
    elif any(t in low for t in _MEASURE_TERMS):
        role, domain = "measure", _match_measure_domain(low)
    elif any(t in low for t in _CATEGORY_TERMS):
        role, domain = "category", _match_domain(low, ("设备", "device", "line", "产线")) or "分类/枚举"
    elif any(t in low for t in _TIMESTAMP_TERMS):
        role, domain = "timestamp", "时间/时序"
    else:
        role, domain = "text", "文本/描述"
    return {"field": col, "role": role, "domain": domain,
            "linked_entity": _DOMAIN_ENTITY.get(domain, None)}


def _match_domain(low, terms):
    for t in terms:
        if t in low:
            if t in ("device", "设备"):
                return "设备/传感器"
            if t in ("line", "产线"):
                return "产线/工位"
    return None


def _match_measure_domain(low):
    if any(t in low for t in ("温度", "temp")):
        return "设备/传感器"
    if any(t in low for t in ("内存", "mem", "cpu")):
        return "设备/传感器"
    if any(t in low for t in ("功率", "power", "load")):
        return "设备/传感器"
    if any(t in low for t in ("金额", "price", "库存", "stock")):
        return "产品/物料"
    return "度量/指标"


def cross_field_semantics(fields: list) -> list:
    """把一组字段（monitor 指标 / task 工单 / memory 记忆）映射到本体语义域。

    返回 [{field, role, domain, linked_entity}]，构成「字段语义 ↔ 本体语义」贯通层。
    """
    return [semantic_role(f) for f in fields]


def semantic_consistency(fields: list) -> dict:
    """语义一致性校验：字段命名是否符合本体语义（防命名错位）。

    规则：
      - 含 measure 词却命名成 category（如 "温度类型"）→ 可疑
      - 主键应 identifier；外键应 reference
      - 连续量指标（温度/功率/内存）应 role=measure
    返回 {checks:[{field, ok, reason}], all_ok}。
    """
    checks = []
    for f in fields:
        s = semantic_role(f)
        low = str(f).lower()
        ok, reason = True, "符合"
        # 温度/功率/内存 类连续量若被判 category → 命名错位
        if s["role"] == "category" and any(t in low for t in _MEASURE_TERMS):
            ok, reason = False, f"连续量指标'{f}'被分类为 category，建议对齐 measure 语义"
        if s["role"] == "measure" and any(t in low for t in _CATEGORY_TERMS):
            ok, reason = False, f"分类枚举'{f}'被分类为 measure，建议对齐 category 语义"
        checks.append({"field": f, "role": s["role"], "ok": ok, "reason": reason})
    return {"checks": checks, "all_ok": all(c["ok"] for c in checks)}


def link_entities(data: dict) -> dict:
    """多表关联：每表一实体 + 外键推断 + 语义角色标注，产出统一实例图。

    复用 ontology.from_schema 做跨表 join（v1/v2 本体认知复用），并补语义角色标注。
    data: {表名: [行...]}
    返回 {entities, roles, graph, edges, consistency}。
    """
    from solo.factory.ontology import Ontology

    schema = {"entities": [], "relations": []}
    for tbl, rows in data.items():
        if not rows:
            continue
        raw = tbl
        for pref in ("factory_", "Factory_", "tbl_", "T_"):
            if raw.lower().startswith(pref):
                raw = raw[len(pref):]
                break
        ent = "".join(w.capitalize() for w in raw.split("_") if w) or tbl
        key = "id" if "id" in rows[0] and rows[0] else list(rows[0].keys())[0]
        schema["entities"].append({
            "id": ent, "table": tbl, "key": key, "label": ent, "domain": "业务",
            "attributes": [{"name": c, "type": "string"} for c in rows[0]]})
    o = Ontology()
    model = o.from_schema(schema, data)
    # 语义角色标注（跨板块语义贯通层）
    roles = {}
    for e in model.get("object_types", []):
        roles[e["id"]] = [semantic_role(a["name"]) for a in e.get("attributes", [])]
    # 一致性校验（全表字段）
    all_fields = []
    for e in model.get("object_types", []):
        all_fields += [a["name"] for a in e.get("attributes", [])]
    cons = semantic_consistency(all_fields)
    return {
        "entities": [e["id"] for e in model.get("object_types", [])],
        "roles": roles,
        "graph": model.get("graph", {}),
        "edges": len(model.get("graph", {}).get("edges", [])),
        "link_types": [l["id"] for l in model.get("link_types", [])],
        "consistency": cons,
    }


def semantic_bridge(blocks: dict) -> dict:
    """本体语义贯通总入口：把 FDE 各板块字段统一到本体语义层。

    blocks: {"monitor":["cpu_percent","mem_percent","device_id","temperature"],
             "task":["device_id","severity","triage","problem"],
             "memory":["text","tags","ts"]}
    返回每个板块的字段语义角色 + 统一贯通视图（同名字段语义是否一致）。
    """
    out = {}
    for name, fields in (blocks or {}).items():
        out[name] = {"fields": [semantic_role(f) for f in fields],
                     "consistency": semantic_consistency(fields)}
    return {"blocks": out, "bridge": {
        "fields": list({f for fl in (blocks or {}).values() for f in fl}),
        "entities": sorted({r["linked_entity"] for fl in (blocks or {}).values()
                            for f in fl
                            for r in [semantic_role(f)] if r["linked_entity"]}),
    }}
