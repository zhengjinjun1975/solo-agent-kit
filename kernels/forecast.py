# -*- coding: utf-8 -*-
"""kernels/forecast.py — 预测性维护 纯函数内核。

迁移自 factory/monitor.py 趋势部分 + 深化：MAD 稳健基线、线性/移动平均回归、
RUL 寿命粗估、故障模式→维修建议映射。无状态、确定性。
消费原子：predictive-maintain、sme-decision。
"""
from __future__ import annotations

import math

_FAULT_ADVICE = {
    "轴承磨损": {"actions": ["更换轴承", "检查润滑脂"], "parts": ["轴承", "润滑脂"],
                 "estimated_cost": 1200},
    "轴对中偏差": {"actions": ["重新对中", "检查联轴器"], "parts": ["联轴器"],
                    "estimated_cost": 800},
    "振动越限": {"actions": ["停机检查", "动平衡", "检查松动"], "parts": ["螺栓", "垫片"],
                  "estimated_cost": 1500},
    "温度过高": {"actions": ["检查冷却系统", "清洁散热片"], "parts": ["风扇", "散热片"],
                  "estimated_cost": 600},
    "油液污染": {"actions": ["换油", "清洁滤芯"], "parts": ["润滑油", "滤芯"],
                  "estimated_cost": 500},
    "皮带磨损": {"actions": ["更换皮带", "张紧"], "parts": ["皮带"], "estimated_cost": 400},
}


def mad(values: list) -> float:
    """中位数绝对偏差（稳健离散度）。"""
    vals = [float(v) for v in values if _isnum(v)]
    if not vals:
        return 0.0
    med = sorted(vals)[len(vals) // 2]
    return sorted(abs(v - med) for v in vals)[len(vals) // 2]


def adaptive_threshold(values: list, k: float = 3.0) -> dict:
    """自适应阈值：MAD 稳健基线 + k·MAD（对离群不敏感）。"""
    vals = [float(v) for v in values if _isnum(v)]
    if len(vals) < 3:
        return {"error": "insufficient data"}
    med = sorted(vals)[len(vals) // 2]
    m = mad(vals) or (sum(vals) / len(vals) * 0.1)
    return {"center": round(med, 3), "upper": round(med + k * m, 3),
            "lower": round(med - k * m, 3), "mad": round(m, 3), "k": k}


def linear_regression(values: list) -> dict:
    """线性回归：斜率/截距/相关系数 r。"""
    vals = [float(v) for v in values if _isnum(v)]
    n = len(vals)
    if n < 2:
        return {"slope": 0, "intercept": 0, "r": 0, "direction": "insufficient"}
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(vals) / n
    num = sum((xs[i] - x_mean) * (vals[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n)) or 1
    slope = num / den
    intercept = y_mean - slope * x_mean
    if den and _isnum(sum((vals[i] - y_mean) ** 2 for i in range(n))):
        den_y = sum((vals[i] - y_mean) ** 2 for i in range(n))
        r = (num / math.sqrt(den * den_y)) if (den > 0 and den_y > 0) else 0.0
    else:
        r = 0.0
    return {"slope": round(slope, 4), "intercept": round(intercept, 4),
            "r": round(r, 4),
            "direction": "rising" if slope > 0 else "falling" if slope < 0 else "flat"}


def moving_average(values: list, window: int = 3) -> list:
    vals = [float(v) for v in values if _isnum(v)]
    if len(vals) < window:
        return vals
    return [round(sum(vals[max(0, i - window + 1):i + 1]) /
                  min(window, i + 1), 3) for i in range(len(vals))]


def forecast_series(values: list, horizon: int = 1) -> dict:
    """趋势外推预测：下一值 + 上下界。"""
    reg = linear_regression(values)
    vals = [float(v) for v in values if _isnum(v)]
    n = len(vals)
    if n < 2:
        return {"error": "insufficient data", "trend": reg}
    std = math.sqrt(sum((vals[i] - (reg["slope"] * i + reg["intercept"])) ** 2
                        for i in range(n)) / n)
    next_v = reg["slope"] * n + reg["intercept"]
    return {"trend": reg,
            "next": round(next_v, 3),
            "upper": round(next_v + 2 * std, 3),
            "lower": round(next_v - 2 * std, 3)}


def rul(values: list, threshold: float) -> dict:
    """剩余使用寿命粗估：RUL=(threshold-current)/slope（slope 朝阈值方向才有限）。"""
    vals = [float(v) for v in values if _isnum(v)]
    if len(vals) < 2:
        return {"error": "insufficient data"}
    reg = linear_regression(vals)
    cur = vals[-1]
    slope = reg["slope"]
    if abs(slope) < 1e-9 or (slope > 0) != (threshold > cur):
        return {"rul": None, "trend": reg, "health": _health_index(cur, threshold),
                "note": "趋势未朝阈值方向，RUL 无限/不适用"}
    rul_val = (threshold - cur) / slope
    return {"rul": round(max(0, rul_val), 1), "trend": reg,
            "health": _health_index(cur, threshold)}


def _health_index(current: float, threshold: float) -> float:
    return round(max(0.0, min(1.0, 1 - abs(current) / abs(threshold))), 3) if threshold else 1.0


def fault_advice(failure_mode: str, top_n: int = 3) -> dict:
    """故障模式 → 维修建议（匹配 + 通用兜底）。返回 {actions, parts, estimated_cost}。"""
    key = (failure_mode or "").strip()
    for name, advice in _FAULT_ADVICE.items():
        if name in key or key in name:
            return dict(advice)
    # 通用兜底
    return {"actions": ["停机检查并联系维护", "记录故障现象与信号"], "parts": [],
            "estimated_cost": 0}


def risk_level(predictions: list, warn_pct: float = 0.6, crit_pct: float = 0.9) -> str:
    """基于预测结果给风险等级：critical/high/medium/low。

    基于相对波动(MAD/均值偏差)判定, 不用 cur/max 简单归一化
    (否则近常量数据 cur≈max → cur/max≈1 恒超阈值 → 稳定数据误判 high)。
    稳定(低波动)→low, 波动/趋势明显→high, 极值+上升→critical。
    """
    vals = [float(v) for v in predictions if _isnum(v)]
    if not vals:
        return "low"
    n = len(vals)
    if n == 1:
        return "low"
    # 相对基线: 以中位数/均值为参考, 波动用 MAD(鲁棒)或标准差
    med = sorted(vals)[n // 2]
    mean = sum(vals) / n
    spread = mad(vals) if 'mad' in globals() else max((sum(abs(v - mean) for v in vals) / n), 1e-9)
    if spread < 1e-9:
        spread = max(abs(mean) * 0.05, 1e-9)  # 近常量: 用 5% 均值作尺度, 避免除零
    cur = vals[-1]
    # 相对偏差(当前值偏离基线程度)
    dev = abs(cur - med) / spread
    # 波动度(整体波动相对均值, 波动本身是风险: 设备抖动/不稳定)
    volatility = spread / (abs(mean) + 1e-9)
    # 趋势(最近是否持续上升)
    rising = n >= 3 and vals[-1] > vals[-2] and vals[-2] > vals[-3]
    # 越限: 当前值明显偏离基线
    if dev > 3.0 and rising and cur > med:
        return "critical"
    if dev > 2.5 or (rising and cur > med and dev > 1.5) or volatility > 0.5:
        return "high"
    if dev > 1.5 or volatility > 0.3:
        return "medium"
    return "low"


def _isnum(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
