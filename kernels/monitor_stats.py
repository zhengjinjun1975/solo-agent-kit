# -*- coding: utf-8 -*-
"""kernels/monitor_stats.py — 设备监测 统计纯函数内核。

迁移自 factory/monitor.py 纯函数部分：MAD 稳健基线、自适应阈值、描述统计、
RuleChain 判则纯逻辑（条件匹配）。无状态、确定性。
消费原子：monitor-device。
"""
from __future__ import annotations

import math


def _isnum(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def mad(values: list) -> float:
    vals = [float(v) for v in values if _isnum(v)]
    if not vals:
        return 0.0
    med = sorted(vals)[len(vals) // 2]
    return sorted(abs(v - med) for v in vals)[len(vals) // 2]


def median(values: list) -> float:
    vals = [float(v) for v in values if _isnum(v)]
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def stats(values: list) -> dict:
    vals = [float(v) for v in values if _isnum(v)]
    if not vals:
        return {"count": 0}
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / n
    return {"count": n, "min": round(min(vals), 3), "max": round(max(vals), 3),
            "mean": round(mean, 3), "median": round(median(vals), 3),
            "std": round(math.sqrt(var), 3), "mad": round(mad(vals), 3)}


def adaptive_threshold(values: list, k: float = 3.0) -> dict:
    """自适应动态阈值：MAD 稳健基线 + k·MAD（对离群不敏感，动态自适应）。"""
    vals = [float(v) for v in values if _isnum(v)]
    if len(vals) < 3:
        return {"error": "insufficient data"}
    center = median(vals)
    m = mad(vals) or (center * 0.1 if center else 1.0)
    return {"center": round(center, 3), "upper": round(center + k * m, 3),
            "lower": round(center - k * m, 3), "mad": round(m, 3), "k": k}


def anomaly(values: list, method: str = "mad", k: float = 3.0) -> list:
    """异常检测：MAD z-score 或 zscore。返回异常点列表。"""
    vals = [float(v) for v in values if _isnum(v)]
    if len(vals) < 4:
        return []
    out = []
    if method == "mad":
        center = median(vals)
        m = mad(vals) or 1.0
        for i, v in enumerate(vals):
            if abs(v - center) > k * m:
                out.append({"index": i, "value": round(v, 3),
                            "zscore": round((v - center) / m, 2)})
    else:  # zscore
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals)) or 1
        for i, v in enumerate(vals):
            if abs(v - mean) > k * std:
                out.append({"index": i, "value": round(v, 3),
                            "zscore": round((v - mean) / std, 2)})
    return out


def match_condition(value: float, op: str, threshold: float,
                    op2: str = None, threshold2: float = None) -> bool:
    """RuleChain 判则纯逻辑：op 比较（支持单边/区间）。"""
    value = float(value)
    if op in (">", ">"):
        return value > float(threshold)
    if op == ">=":
        return value >= float(threshold)
    if op in ("<", "<"):
        return value < float(threshold)
    if op == "<=":
        return value <= float(threshold)
    if op == "==":
        return value == float(threshold)
    if op == "between" and op2 is not None:
        return float(threshold) <= value <= float(threshold2)
    if op == "outside" and op2 is not None:
        return not (float(threshold) <= value <= float(threshold2))
    return False


def combine_combos(combos: list, current: dict) -> bool:
    """RuleChain 多条件组合判则：AND 语义。current: {metric: value}。"""
    if not combos:
        return True
    for c in combos:
        metric = c.get("metric")
        if metric not in current:
            return False
        if not match_condition(current[metric], c.get("op", ">"),
                               c.get("threshold", 0),
                               c.get("op2"), c.get("threshold2")):
            return False
    return True
