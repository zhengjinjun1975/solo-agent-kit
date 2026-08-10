# -*- coding: utf-8 -*-
"""decisions.py — 声明式决策规则引擎（融合 SME-decision-ontology）。

企业本体 → 决策规则 → 行动清单。一本体多决策：
- 通用运营公式(领域无关) + config/decisions.json 声明规则
- 换行业只需改 decisions.json(哪些表/哪些公式/哪些阈值)，零 Python
- 每条决策带公式依据(可解释)，确定性零 token

指标(metric) → 通用公式：
  reorder 补货 | shortage 缺货 | slow_turnover 呆滞 | aging 账龄
  warranty 保修/维护 | forecast 预测 | price_compare 比价 | supplier_score 供应商评分

零依赖，标准库。
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

# 通用运营公式指标（领域无关，换行业复用）
_METRICS = {}


def _metric(name):
    """注册指标计算函数。"""
    def deco(fn):
        _METRICS[name] = fn
        return fn
    return deco


@_metric("reorder")
def _reorder(data, rule, thr):
    out = []
    rows = data.get(rule.get("table", "inventory"), [])
    join = rule.get("join_key", "product_id")
    sales = data.get(rule.get("sales_table", "sales"), [])
    for r in rows:
        pid = r.get(join)
        if not pid:
            continue
        stock = float(r.get("stock", 0) or 0)
        safety = float(r.get("safety_stock", thr.get("safety_stock", 14)) or 0)
        lead = float(r.get("lead_time_days", thr.get("lead_time_days", 7)) or 0)
        sl = [s for s in sales if s.get(join) == pid and s.get("qty")]
        daily = (sum(float(s.get("qty", 0)) for s in sl) / len({s.get("date") for s in sl})) if sl else 0.0
        rl = daily * lead + safety
        if stock < rl:
            out.append({"entity": pid, "action": rule.get("action", "补货"),
                        "reason": rule.get("reason", f"stock={stock:g} < reorder_level={rl:g} (日均出库×提前期+安全库存)").format(stock=stock, reorder_level=rl),
                        "level": rule.get("level", "建议")})
    return out


@_metric("shortage")
def _shortage(data, rule, thr):
    out = []
    for r in data.get(rule.get("table", "inventory"), []):
        pid = r.get("product_id")
        if not pid:
            continue
        stock = float(r.get("stock", 0) or 0)
        safety = float(r.get("safety_stock", thr.get("safety_stock", 14)) or 0)
        if stock < safety:
            out.append({"entity": pid, "action": rule.get("action", "缺货预警"),
                        "reason": f"stock={stock:g} < safety={safety:g}", "level": rule.get("level", "预警")})
    return out


@_metric("slow_turnover")
def _slow_turnover(data, rule, thr):
    out = []
    sales = data.get("sales", [])
    threshold = float(thr.get("slow_turnover", 1.0))
    for r in data.get("inventory", []):
        pid = r.get("product_id")
        stock = float(r.get("stock", 0) or 0)
        if stock <= 0:
            continue
        sl = [s for s in sales if s.get("product_id") == pid and s.get("qty")]
        out_qty = sum(float(s.get("qty", 0)) for s in sl)
        turnover = out_qty / stock
        if turnover < threshold:
            out.append({"entity": pid, "action": rule.get("action", "呆滞处理"),
                        "reason": f"周转率={turnover:.3f} < 阈值{threshold:g}", "level": rule.get("level", "预警")})
    return out


@_metric("aging")
def _aging(data, rule, thr):
    out = []
    warn = int(thr.get("aging_warn", 60))
    crit = int(thr.get("aging_critical", 90))
    for c in data.get(rule.get("table", "customers"), []):
        cid = c.get("id")
        aging = float(c.get("aging_days", 0) or 0)
        credit = float(c.get("credit_limit", 0) or 0)
        amount = float(c.get("order_amount", 0) or 0)
        if aging >= crit:
            out.append({"entity": cid, "action": "催收告急", "reason": f"账龄{aging:g}天≥{crit}天", "level": "告急"})
        elif aging >= warn:
            out.append({"entity": cid, "action": "催收预警", "reason": f"账龄{aging:g}天≥{warn}天", "level": "预警"})
        elif amount > credit:
            out.append({"entity": cid, "action": "超信用额度", "reason": f"欠款{amount:g}>额度{credit:g}", "level": "预警"})
    return out


@_metric("warranty")
def _warranty(data, rule, thr):
    out = []
    warn = int(thr.get("warranty_warn_days", 60))
    today = date.today()
    for e in data.get(rule.get("table", "equipment"), []):
        eid = e.get("id")
        status = e.get("status", "")
        if status in ("待修", "待维护"):
            out.append({"entity": eid, "action": "维护告急", "reason": f"状态: {status}", "level": "告急"})
            continue
        install = e.get("install_date", "")
        months = int(e.get("warranty_months", 0) or 0)
        try:
            end = date.fromisoformat(install[:10]) + timedelta(days=months * 30)
        except (ValueError, TypeError):
            continue
        left = (end - today).days
        if left < 0:
            out.append({"entity": eid, "action": "保修过期", "reason": f"保修已于{end}到期", "level": "预警"})
        elif left <= warn:
            out.append({"entity": eid, "action": "保修临期", "reason": f"保修{left}天后到期", "level": "建议"})
    return out


@_metric("forecast")
def _forecast(data, rule, thr):
    from collections import defaultdict
    out = []
    window = int(thr.get("forecast_window", 4))
    drop = float(thr.get("forecast_drop", 0.3))
    sales = data.get("sales", [])
    by_p = defaultdict(list)
    for s in sales:
        by_p[s.get("product_id")].append(s)
    for pid, rows in by_p.items():
        rows.sort(key=lambda x: x.get("date", ""))
        if len(rows) < 2:
            continue
        half = max(1, len(rows) // 2)
        recent = sum(float(r.get("qty", 0)) for r in rows[-half:])
        earlier = sum(float(r.get("qty", 0)) for r in rows[:half])
        if earlier > 0 and (earlier - recent) / earlier > drop:
            out.append({"entity": pid, "action": "销售下滑预警",
                        "reason": f"近期销量比前期降{(earlier-recent)/earlier*100:.0f}%", "level": "预警"})
    return out


@_metric("price_compare")
def _price_compare(data, rule, thr):
    out = []
    for p in data.get("products", []):
        sid = p.get("supplier")
        sup = next((s for s in data.get("suppliers", []) if s.get("id") == sid), None)
        if sup:
            out.append({"entity": p.get("id"), "action": "比价提示",
                        "reason": f"产品{p.get('id')} 供应商{sup.get('name')} 价格{sup.get('price_rank','')}",
                        "level": "建议"})
    return out


@_metric("supplier_score")
def _supplier_score(data, rule, thr):
    out = []
    score_thr = float(thr.get("supplier_score", 70))
    for s in data.get("suppliers", []):
        on_time = float(s.get("on_time_pct", 100))
        quality = float(s.get("quality_pct", 100))
        score = on_time * 0.5 + quality * 0.5
        if score < score_thr:
            out.append({"entity": s.get("id"), "action": "供应商绩效预警",
                        "reason": f"评分{score:.1f}<阈值{score_thr:g}(准时{on_time:g}/合格{quality:g})",
                        "level": "预警"})
    return out


def run_decisions(data: dict, rules_path: str = None, model: dict = None) -> dict:
    """执行声明式决策规则，返回可解释行动清单。

    data: {表名: [行...]}
    rules_path: decisions.json（默认 ~/.solo/decisions.json，可复制默认）
    model: 可选本体模型（ontology.from_schema 返回），自动提取企业实体表名，
           用于决策与本体打通（哪些实体参与决策）。
    返回: {"decisions": [...], "total": N, "entities": 参与决策的企业实体}
    """
    rules_path = rules_path or os.path.join(os.path.expanduser("~"), ".solo", "decisions.json")
    if not os.path.exists(rules_path):
        rules_path = _DEFAULT_RULES  # 回退内置默认规则
    rules = json.load(open(rules_path, encoding="utf-8"))
    thresholds = rules.get("_thresholds", {})
    decisions = []
    for module, cfg in rules.items():
        if module.startswith("_"):
            continue
        for rule in cfg.get("rules", []):
            fn = _METRICS.get(rule.get("metric"))
            if not fn:
                continue
            thr = thresholds.get(module, {})
            for d in fn(data, rule, thr):
                decisions.append({"module": module, "id": rule.get("id", ""),
                                  "name": rule.get("name", ""), **d})
    # 本体打通：提取参与决策的企业实体（从本体 model）
    entities = []
    if model and model.get("object_types"):
        for ot in model["object_types"]:
            entities.append({"id": ot.get("id"), "table": ot.get("table"),
                             "label": ot.get("label", ot.get("id"))})
    return {"decisions": decisions, "total": len(decisions), "entities": entities}


# 内置默认规则（复制到 ~/.solo/decisions.json 可自定义）
_DEFAULT_RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "decisions.json")
