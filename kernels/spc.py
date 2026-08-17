# -*- coding: utf-8 -*-
"""kernels/spc.py — SPC/CPK/清洗/描述统计/控制图判异 纯函数内核。

迁移自 solo/factory/data.py（去掉 IO 与有状态 DataCleaner.report，只留纯函数）。
无状态、无副作用、确定性。消费原子：data-cap、predictive-maintain。
"""
from __future__ import annotations

import math
import re


# ---- 数值原语 ----
def is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def quantile(vals: list, q: float) -> float:
    s = sorted(float(v) for v in vals)
    if not s:
        return 0.0
    idx = (len(s) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 3)


def guess_type(value: str) -> str:
    """猜值类型：空/整数/浮点/日期/文本。"""
    v = (value or "").strip()
    if not v:
        return "missing"
    if re.fullmatch(r"-?\d+", v):
        return "integer"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "float"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "date"
    return "text"


# ---- 清洗（去 IO 版：rows 进出，返回 (cleaned_rows, metrics)）----
def clean(rows: list, numeric_cols: list = None,
          fill_missing: str = "drop", outlier_method: str = "iqr"):
    """清洗主流程（纯函数）。返回 (cleaned_rows, report_metrics)。"""
    metrics = {"rows": len(rows), "dropped_dup": 0, "filled_missing": 0,
               "dropped_outlier": 0, "types": {}, "missing_by_col": {}}
    if not rows:
        return rows, metrics

    cols = list(rows[0].keys())
    types = {}
    for c in cols:
        non_missing = [r.get(c, "").strip() for r in rows if str(r.get(c, "")).strip()]
        if non_missing:
            types[c] = guess_type(non_missing[0])
    metrics["types"] = types

    num_cols = numeric_cols or [c for c, t in types.items() if t in ("integer", "float")]
    for c in num_cols:
        vals = []
        for r in rows:
            v = str(r.get(c, "")).strip()
            if v and is_num(v):
                vals.append(float(v))
        if vals:
            metrics["missing_by_col"][c] = len([r for r in rows
                                                if not str(r.get(c, "")).strip()])

    # 1 去重
    seen = set()
    dedup = []
    for r in rows:
        key = tuple(sorted((k, str(r.get(k, ""))) for k in r))
        if key in seen:
            metrics["dropped_dup"] += 1
            continue
        seen.add(key)
        dedup.append(r)
    rows = dedup

    # 2 缺失值处理
    cleaned = []
    for r in rows:
        row = dict(r)
        skip = False
        for c in cols:
            if not str(row.get(c, "")).strip():
                if fill_missing == "drop":
                    skip = True
                    break
                elif fill_missing == "zero":
                    row[c] = "0"
                    metrics["filled_missing"] += 1
                elif fill_missing == "mean" and c in num_cols:
                    vals = [float(x.get(c)) for x in rows
                            if str(x.get(c, "")).strip() and is_num(x.get(c))]
                    row[c] = str(sum(vals) / len(vals)) if vals else "0"
                    metrics["filled_missing"] += 1
        if not skip:
            cleaned.append(row)
    rows = cleaned

    # 3 异常值处理
    if outlier_method == "iqr":
        rows, d = _outlier_iqr(rows, num_cols)
    elif outlier_method == "zscore":
        rows, d = _outlier_zscore(rows, num_cols)
    else:
        d = 0
    metrics["dropped_outlier"] += d
    return rows, metrics


def _outlier_iqr(rows: list, num_cols: list):
    to_drop = set()
    for c in num_cols:
        vals = [float(r[c]) for r in rows if is_num(r.get(c))]
        if len(vals) < 4:
            continue
        q1, q3 = quantile(vals, 0.25), quantile(vals, 0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        for idx, r in enumerate(rows):
            if is_num(r.get(c)) and not (lo <= float(r[c]) <= hi):
                to_drop.add(idx)
    return [r for i, r in enumerate(rows) if i not in to_drop], len(to_drop)


def _outlier_zscore(rows: list, num_cols: list):
    dropped = 0
    for c in num_cols:
        vals = [float(r[c]) for r in rows if is_num(r.get(c))]
        if len(vals) < 3:
            continue
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 1
        before = len(rows)
        rows = [r for r in rows if not (is_num(r.get(c)) and abs(float(r[c]) - mean) > 3 * std)]
        dropped += before - len(rows)
    return rows, dropped


# ---- 描述统计 ----
def describe(values: list) -> dict:
    vals = [float(v) for v in values if is_num(v)]
    if not vals:
        return {"count": 0}
    s = sorted(vals)
    n = len(s)
    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / n
    return {
        "count": n, "min": s[0], "max": s[-1], "mean": round(mean, 3),
        "median": quantile(s, 0.5), "std": round(math.sqrt(var), 3),
        "p25": quantile(s, 0.25), "p75": quantile(s, 0.75),
    }


def trend(values: list) -> dict:
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
    direction = ("rising" if slope > 0.01 * (y_mean or 1)
                 else "falling" if slope < -0.01 * (y_mean or 1) else "flat")
    return {"slope": round(slope, 4), "direction": direction}


def detect_anomaly(values: list, method: str = "zscore", threshold: float = 3.0) -> list:
    vals = [float(v) for v in values if is_num(v)]
    if len(vals) < 4:
        return []
    anomalies = []
    if method == "zscore":
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals)) or 1
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
    """SPC X-bar 控制图：中心线 + UCL/LCL + 判异（出界/连串/趋势）。"""
    vals = [float(v) for v in values if is_num(v)]
    if len(vals) < 2:
        return {"error": "insufficient data"}
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals))
    ucl, lcl = mean + 3 * std, mean - 3 * std
    out_of_control = [{"index": i, "value": round(v, 3),
                       "violation": "UCL" if v > ucl else "LCL"}
                      for i, v in enumerate(vals) if v > ucl or v < lcl]
    # 连串判异：连续 7 点在中心线同侧 → 判异
    run_detected = None
    if len(vals) >= 7:
        for start in range(len(vals) - 6):
            run = vals[start:start + 7]
            if all(v > mean for v in run) or all(v < mean for v in run):
                run_detected = {"start": start, "side": "above" if run[0] > mean else "below"}
                break
    # 趋势判异：连续 6 点递增或递减
    trend_detected = None
    if len(vals) >= 6:
        for start in range(len(vals) - 5):
            seg = vals[start:start + 6]
            if all(seg[i] < seg[i + 1] for i in range(5)):
                trend_detected = {"start": start, "direction": "rising"}
                break
            if all(seg[i] > seg[i + 1] for i in range(5)):
                trend_detected = {"start": start, "direction": "falling"}
                break
    judge = "失控" if (out_of_control or run_detected or trend_detected) else "受控"
    points = [{"index": i, "value": round(v, 3)} for i, v in enumerate(vals[:100])]
    return {
        "mean": round(mean, 3), "std": round(std, 3), "ucl": round(ucl, 3),
        "lcl": round(lcl, 3), "out_of_control": out_of_control,
        "run_detected": run_detected, "trend_detected": trend_detected,
        "judge": judge, "points": points,
    }


def cpk(values: list, usl: float = None, lsl: float = None) -> dict:
    """过程能力指数：Cp / Cpk（USL/LSL 规格限）。"""
    vals = [float(v) for v in values if is_num(v)]
    if len(vals) < 4:
        return {"error": "insufficient data"}
    mean = sum(vals) / len(vals)
    std = math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals)) or 1e-9
    cp = None
    if usl is not None and lsl is not None and (usl - lsl) > 0:
        cp = round((usl - lsl) / (6 * std), 3)
    cpu = round((usl - mean) / (3 * std), 3) if usl is not None else None
    cpl = round((mean - lsl) / (3 * std), 3) if lsl is not None else None
    cpk_v = min(x for x in (cpu, cpl) if x is not None) if (cpu is not None or cpl is not None) else None
    judge = None
    if cpk_v is not None:
        judge = ("能力不足" if cpk_v < 1.0 else
                 "能力尚可" if cpk_v < 1.33 else "能力充分")
    return {"cp": cp, "cpk": cpk_v, "cpu": cpu, "cpl": cpl,
            "sigma": round(std, 3), "mean": round(mean, 3), "judge": judge}


# ---- 数据审视（纯函数）----
_FIELD_CN = {
    "id": "编号", "name": "名称", "type": "类型", "status": "状态",
    "temp": "温度", "temperature": "温度", "time": "时间", "date": "日期",
    "power": "功率", "pressure": "压力", "vibration": "振动", "value": "数值",
    "speed": "速度", "humidity": "湿度", "flow": "流量", "count": "数量",
    "qty": "数量", "remark": "备注", "desc": "描述", "location": "位置",
    "device": "设备", "sensor": "传感器", "voltage": "电压", "current": "电流",
}


def _field_cn(column: str) -> str:
    words = re.split(r"[_\\s]+", column.strip())
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ",
                   " ".join(w for w in words if w)).split()
    return "".join(_FIELD_CN.get(w.lower(), "") for w in words) or column


def schema(rows: list) -> dict:
    if not rows:
        return {"columns": [], "total_rows": 0, "fields": {}}
    total = len(rows)
    fields = {}
    for c in rows[0].keys():
        vals = [str(r.get(c, "")).strip() for r in rows]
        non_empty = [v for v in vals if v]
        fields[c] = {"type": guess_type(non_empty[0]) if non_empty else "empty",
                     "non_empty": len(non_empty), "missing": total - len(non_empty),
                     "unique": len(set(vals)), "sample": non_empty[:5]}
    return {"columns": list(rows[0].keys()), "total_rows": total, "fields": fields}


def dictionary(rows: list) -> dict:
    if not rows:
        return {"columns": [], "total_rows": 0, "fields": {}}
    total = len(rows)
    fields = {}
    for c in rows[0].keys():
        vals = [str(r.get(c, "")).strip() for r in rows]
        non_empty = [v for v in vals if v]
        uniq = sorted(set(vals))
        t = guess_type(non_empty[0]) if non_empty else "empty"
        enum = uniq[:20] if 0 < len(uniq) <= 20 and len(uniq) < total else []
        fields[c] = {"name": c, "cn": _field_cn(c), "type": t,
                     "caliber": f"该字段 {len(non_empty)}/{total} 个非空值，{len(uniq)} 个不同取值",
                     "enum": enum}
    return {"columns": list(rows[0].keys()), "total_rows": total, "fields": fields}


def quality(rows: list) -> dict:
    if not rows:
        return {"ok": True, "issues": [], "metrics": {"rows": 0}}
    total = len(rows)
    cols = list(rows[0].keys())
    issues = []
    missing = {}
    for c in cols:
        m = sum(1 for r in rows if not str(r.get(c, "")).strip())
        if m:
            missing[c] = m
            issues.append({"level": "warn", "type": "missing", "column": c,
                           "count": m, "rate": round(m / total, 3)})
    seen = set()
    dups = 0
    for r in rows:
        key = tuple(str(r.get(c, "")) for c in cols)
        if key in seen:
            dups += 1
        else:
            seen.add(key)
    if dups:
        issues.append({"level": "warn", "type": "duplicate", "count": dups,
                       "rate": round(dups / total, 3)})
    drift = []
    outlier_total = 0
    for c in cols:
        vals = [r.get(c, "") for r in rows]
        non_empty = [str(v) for v in vals if str(v).strip()]
        if not non_empty:
            continue
        t0 = guess_type(non_empty[0])
        drifted = [v for v in non_empty if guess_type(v) != t0]
        if drifted and t0 in ("integer", "float"):
            drift.append({"column": c, "type": t0, "count": len(drifted)})
            issues.append({"level": "warn", "type": "type_drift", "column": c,
                           "count": len(drifted)})
        nums = [float(r[c]) for r in rows if is_num(r.get(c))]
        if len(nums) >= 4:
            outlier_total += len(detect_anomaly(nums, method="iqr"))
    if outlier_total:
        issues.append({"level": "warn", "type": "outlier", "count": outlier_total})
    return {
        "ok": len(issues) == 0, "total_rows": total, "total_cols": len(cols),
        "metrics": {"rows": total, "missing_total": sum(missing.values()),
                    "duplicates": dups, "outliers": outlier_total},
        "missing": missing, "type_drift": drift, "issues": issues,
    }


def report(rows: list) -> dict:
    return {"schema": schema(rows), "dictionary": dictionary(rows),
            "quality": quality(rows), "preview": rows[:5]}
