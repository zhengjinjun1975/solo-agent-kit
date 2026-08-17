# -*- coding: utf-8 -*-
"""kernels/rules.py — 决策规则引擎 + 严重度规则 纯函数内核。

迁移自 factory/decisions.py 的 run_decisions/_METRICS 规则 + 阈值深合并，
并加入工单严重度判定、故障模式映射。无状态、确定性。
消费原子：sme-decision、diagnose-kb、fde-task。
"""
from __future__ import annotations

import math


# ---- 决策规则（通用运营公式，领域无关）----
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
        days = {s.get("date") for s in sl}
        daily = (sum(float(s.get("qty", 0)) for s in sl) / len(days)) if (sl and days) else 0.0
        rl = daily * lead + safety
        if stock < rl:
            out.append({"entity": pid, "action": rule.get("action", "补货"),
                        "reason": f"stock={stock:g} < reorder_level={rl:g} "
                                  f"(日均出库×提前期+安全库存)",
                        "level": rule.get("level", "建议")})
    return out


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
                        "reason": f"stock={stock:g} < safety={safety:g}",
                        "level": rule.get("level", "预警")})
    return out


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
                        "reason": f"周转率={turnover:.3f} < 阈值{threshold:g}",
                        "level": rule.get("level", "预警")})
    return out


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
            out.append({"entity": cid, "action": "催收告急",
                        "reason": f"账龄{aging:g}天≥{crit}天", "level": "告急"})
        elif aging >= warn:
            out.append({"entity": cid, "action": "催收预警",
                        "reason": f"账龄{aging:g}天≥{warn}天", "level": "预警"})
        elif amount > credit:
            out.append({"entity": cid, "action": "超信用额度",
                        "reason": f"欠款{amount:g}>额度{credit:g}", "level": "预警"})
    return out


def _warranty(data, rule, thr):
    from datetime import date, timedelta
    out = []
    warn = int(thr.get("warranty_warn_days", 60))
    today = date.today()
    for e in data.get(rule.get("table", "equipment"), []):
        eid = e.get("id")
        status = e.get("status", "")
        if status in ("待修", "待维护"):
            out.append({"entity": eid, "action": "维护告急",
                        "reason": f"状态: {status}", "level": "告急"})
            continue
        install = e.get("install_date", "")
        months = int(e.get("warranty_months", 0) or 0)
        try:
            end = date.fromisoformat(install[:10]) + timedelta(days=months * 30)
        except (ValueError, TypeError):
            continue
        left = (end - today).days
        if left < 0:
            out.append({"entity": eid, "action": "保修过期",
                        "reason": f"保修已于{end}到期", "level": "预警"})
        elif left <= warn:
            out.append({"entity": eid, "action": "保修临期",
                        "reason": f"保修{left}天后到期", "level": "建议"})
    return out


def _forecast(data, rule, thr):
    from collections import defaultdict
    out = []
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
                        "reason": f"近期销量比前期降{(earlier - recent) / earlier * 100:.0f}%",
                        "level": "预警"})
    return out


def _price_compare(data, rule, thr):
    out = []
    for p in data.get("products", []):
        sid = p.get("supplier")
        sup = next((s for s in data.get("suppliers", []) if s.get("id") == sid), None)
        if sup:
            out.append({"entity": p.get("id"), "action": "比价提示",
                        "reason": f"产品{p.get('id')} 供应商{sup.get('name')} "
                                  f"价格{sup.get('price_rank', '')}",
                        "level": "建议"})
    return out


def _supplier_score(data, rule, thr):
    out = []
    score_thr = float(thr.get("supplier_score", 70))
    for s in data.get("suppliers", []):
        on_time = float(s.get("on_time_pct", 100))
        quality = float(s.get("quality_pct", 100))
        score = on_time * 0.5 + quality * 0.5
        if score < score_thr:
            out.append({"entity": s.get("id"), "action": "供应商绩效预警",
                        "reason": f"评分{score:.1f}<阈值{score_thr:g}"
                                  f"(准时{on_time:g}/合格{quality:g})",
                        "level": "预警"})
    return out


_METRICS = {
    "reorder": _reorder, "shortage": _shortage, "slow_turnover": _slow_turnover,
    "aging": _aging, "warranty": _warranty, "forecast": _forecast,
    "price_compare": _price_compare, "supplier_score": _supplier_score,
}


def deep_merge_thresholds(base: dict, override: dict) -> dict:
    """阈值深合并：override 覆盖 base，支持多级（模块→键）。"""
    out = dict(base)
    for module, thr in (override or {}).items():
        if isinstance(thr, dict):
            merged = dict(out.get(module, {}) or {})
            merged.update(thr)
            out[module] = merged
        else:
            out[module] = thr
    return out


def run_decisions(data: dict, rules: dict, thresholds: dict = None) -> dict:
    """执行声明式决策规则（纯函数，rules 为已解析配置，thresholds 为合并后阈值表）。

    rules: {"module": {"rules":[{metric,id,name,table,action,level,reason}],...}}
    返回 {"decisions", "total", "entities"}。
    """
    thresholds = thresholds or {}
    decisions = []
    for module, cfg in (rules or {}).items():
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
    return {"decisions": decisions, "total": len(decisions)}


# ---- 工单严重度规则 ----
def severity_from_alerts(alerts: list) -> str:
    """根据告警列表判定工单严重度：critical→critical，warn→high，else medium。"""
    levels = [a.get("level", "") for a in (alerts or [])]
    if any(l == "critical" for l in levels):
        return "critical"
    if any(l in ("warn", "high") for l in levels):
        return "high"
    return "medium"


def severity_rules() -> dict:
    """严重度判定规则（供 fde-task 使用）。"""
    return {
        "critical": ["critical"],
        "high": ["high", "warn"],
        "medium": ["medium", "info"],
    }
