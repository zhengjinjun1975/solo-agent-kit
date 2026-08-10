# -*- coding: utf-8 -*-
"""stats.py — 工厂数据分析（零依赖，标准库）。

方法论（SPC 统计过程控制 + 工业时序分析）：
工厂数据清洗后，需要：描述性统计 / 趋势 / 异常检测 / 控制图。
能力对齐 FDE：帮现场判断"设备状态是否正常、趋势是否异常"。

零依赖：纯标准库实现均值/方差/中位数/相关性/异常检测。
"""
from __future__ import annotations

import math

from solo._util import is_num, quantile


def describe(values: list) -> dict:
    """描述性统计：count/min/max/mean/median/std/p25/p75。"""
    vals = [float(v) for v in values if is_num(v)]
    if not vals:
        return {"count": 0}
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / n
    return {
        "count": n,
        "min": s[0],
        "max": s[-1],
        "mean": round(mean, 3),
        "median": quantile(s, 0.5),
        "std": round(math.sqrt(var), 3),
        "p25": quantile(s, 0.25),
        "p75": quantile(s, 0.75),
    }


def describe_stream(values) -> dict:
    """P2-5: 流式描述统计（Welford 在线算法，O(1) 内存，大文件友好）。

    values 可为迭代器/生成器（逐值 yield），不整列入内存。
    """
    count = 0
    mean = 0.0
    m2 = 0.0
    minv = None
    maxv = None
    for v in values:
        try:
            x = float(v)
        except (ValueError, TypeError):
            continue
        count += 1
        delta = x - mean
        mean += delta / count
        m2 += delta * (x - mean)
        if minv is None or x < minv:
            minv = x
        if maxv is None or x > maxv:
            maxv = x
    if count == 0:
        return {"count": 0}
    variance = m2 / count if count > 1 else 0.0
    return {
        "count": count,
        "min": minv,
        "max": maxv,
        "mean": round(mean, 3),
        "std": round(math.sqrt(variance), 3),
        # 流式无法算精确中位数/分位数（需排序），标注 O(1) 内存近似
        "streaming": True,
    }


def trend(values: list) -> dict:
    """趋势分析：线性回归斜率（判断上升/下降/平稳）。"""
    xs = list(range(len(values)))
    vals = [float(v) for v in values if is_num(v)]
    if len(vals) < 2:
        return {"slope": 0, "direction": "insufficient"}
    n = len(vals)
    x_mean = sum(xs[:n]) / n
    y_mean = sum(vals) / n
    num = sum((xs[i] - x_mean) * (vals[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n)) or 1
    slope = num / den
    direction = "rising" if slope > 0.01 * (y_mean or 1) else ("falling" if slope < -0.01 * (y_mean or 1) else "flat")
    return {"slope": round(slope, 4), "direction": direction}


def detect_anomaly(values: list, method: str = "zscore", threshold: float = 3.0) -> list:
    """异常检测：返回异常点索引+值。

    method: 'zscore' 距均值>3σ / 'iqr' 超出 Q1-1.5IQR 到 Q3+1.5IQR
    空数据或数据过少返回 []（防 IndexError）。
    """
    vals = [float(v) for v in values if is_num(v)]
    if len(vals) < 4:  # IQR 需要至少 4 个值；zscore 需至少 3 个，统一防护
        return []
    anomalies = []
    if method == "zscore":
        mean = sum(vals) / len(vals) if vals else 0
        std = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals)) if vals else 1
        for i, v in enumerate(vals):
            if abs(v - mean) > threshold * (std or 1):
                anomalies.append({"index": i, "value": round(v, 3),
                                  "zscore": round((v - mean) / (std or 1), 2)})
    elif method == "iqr":
        q1, q3 = quantile(vals, 0.25), quantile(vals, 0.75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for i, v in enumerate(vals):
            if not (lo <= v <= hi):
                anomalies.append({"index": i, "value": round(v, 3)})
    return anomalies


def control_chart(values: list) -> dict:
    """SPC 控制图（X-bar 图）：中心线 + 上下控制限。

    UCL = mean + 3*σ, LCL = mean - 3*σ（工厂过程控制标准）。
    返回控制限 + 是否失控（越限点）。
    """
    vals = [float(v) for v in values if is_num(v)]
    if len(vals) < 2:
        return {"error": "insufficient data"}
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals))
    ucl, lcl = mean + 3 * std, mean - 3 * std
    out_of_control = [{"index": i, "value": round(v, 3), "violation": "UCL" if v > ucl else "LCL"}
                      for i, v in enumerate(vals) if v > ucl or v < lcl]
    # 数据点序列（供前端画真实折线，最多取前100点避免过大）
    points = [{"index": i, "value": round(v, 3)} for i, v in enumerate(vals[:100])]
    return {
        "mean": round(mean, 3), "std": round(std, 3),
        "ucl": round(ucl, 3), "lcl": round(lcl, 3),
        "out_of_control": out_of_control, "points": points,
    }


def correlation(a: list, b: list) -> float:
    """皮尔逊相关系数（两列相关，如温度↔能耗）。"""
    x = [float(i) for i in a if is_num(i)]
    y = [float(i) for i in b if is_num(i)]
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x, y = x[:n], y[:n]
    mx, my = sum(x) / n, sum(y) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = math.sqrt(sum((v - mx) ** 2 for v in x))
    dy = math.sqrt(sum((v - my) ** 2 for v in y))
    return round(num / (dx * dy or 1), 3)



