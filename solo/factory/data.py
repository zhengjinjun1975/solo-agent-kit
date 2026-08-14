# -*- coding: utf-8 -*-
"""data.py — 工厂数据审视完整能力（数据清洗 + 数据分析 + 数据审计）。

方法论（Cleanits + SPC 统计过程控制 + 工业数据预处理最佳实践 + pandas-profiling）：
工厂现场数据（MES/SCADA/传感器）脏、缺、噪，审视（清洗→分析→审计）是建模的前提。

同一概念域「对 rows 做审视」的三个切片合并于此，共享同一套数值原语
（is_num/quantile/guess_type，从 solo.base 一次引入），避免各模块重复拼装：
  - clean   数据清洗（缺失/重复/异常值/类型推断）  → DataCleaner / guess_type
  - stats   数据分析（描述/趋势/异常/SPC控制图）   → describe / trend / detect_anomaly / control_chart
  - audit   数据审计（盘点/字典/质量/一键报告）    → schema / dictionary / quality / report

对齐 FDE：给工厂现场数据做第一道工序，为 stats 分析和 ontology 建模喂干净数据。
零依赖（仅标准库 + solo.base 数值工具）。
"""
from __future__ import annotations

import csv
import math
import re

from solo.base import is_num, quantile


# ═══════════════════════════ 共享数值原语 ═══════════════════════════
# is_num / quantile 已从 solo.base 一次引入，供 clean/stats/audit 共用。
# guess_type 在此实现（原 clean 独有，audit 也依赖）。

def guess_type(value: str) -> str:
    """猜值类型：空/整数/浮点/日期/文本。"""
    v = value.strip()
    if not v:
        return "missing"
    if re.fullmatch(r"-?\d+", v):
        return "integer"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "float"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "date"
    return "text"


# ═══════════════════════════ 1. clean：数据清洗 ═══════════════════════════
class DataCleaner:
    """工厂数据清洗器。输入 CSV/行列表，输出干净数据 + 清洗报告。

    报告含：缺失率 / 重复数 / 异常值数 / 每列类型——让 FDE 知道数据到底多脏。
    """

    def __init__(self):
        self.report = {"rows": 0, "dropped_dup": 0, "filled_missing": 0,
                       "dropped_outlier": 0, "types": {}, "missing_by_col": {}}

    def load_csv(self, path: str) -> list:
        """读 CSV 为行列表（list[dict]）。"""
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def clean(self, rows: list, numeric_cols: list = None,
              fill_missing: str = "drop", outlier_method: str = "iqr") -> list:
        """清洗主流程。

        fill_missing: 'drop'删缺失行 / 'zero'填0 / 'mean'填均值
        outlier_method: 'iqr'四分位距 / 'zscore'标准差
        numeric_cols: 指定数值列；None 自动推断
        """
        self.report["rows"] = len(rows)
        if not rows:
            return rows

        cols = rows[0].keys()
        # 类型推断（跳过缺失）
        types = {}
        for c in cols:
            non_missing = [r.get(c, "").strip() for r in rows if r.get(c, "").strip()]
            if non_missing:
                types[c] = guess_type(non_missing[0])
        self.report["types"] = types

        # 数值列（自动推断或指定）
        num_cols = numeric_cols or [c for c, t in types.items() if t in ("integer", "float")]
        for c in num_cols:
            vals = []
            for r in rows:
                v = r.get(c, "").strip()
                if v:
                    try:
                        vals.append(float(v))
                    except ValueError:
                        pass
            if vals:
                self.report["missing_by_col"][c] = len([r for r in rows
                                                        if not r.get(c, "").strip()])

        # 1. 去重
        seen = set()
        dedup = []
        for r in rows:
            key = tuple(sorted((k, r.get(k, "")) for k in r))
            if key in seen:
                self.report["dropped_dup"] += 1
                continue
            seen.add(key)
            dedup.append(r)
        rows = dedup

        # 2. 缺失值处理
        cleaned = []
        for r in rows:
            row = dict(r)
            skip = False
            for c in cols:
                if not row.get(c, "").strip():
                    if fill_missing == "drop":
                        skip = True
                        break
                    elif fill_missing == "zero":
                        row[c] = "0"
                        self.report["filled_missing"] += 1
                    elif fill_missing == "mean" and c in num_cols:
                        vals = [float(x.get(c)) for x in rows
                                if x.get(c, "").strip() and is_num(x.get(c))]
                        row[c] = str(sum(vals) / len(vals)) if vals else "0"
                        self.report["filled_missing"] += 1
            if not skip:
                cleaned.append(row)
        rows = cleaned

        # 3. 异常值处理（数值列，IQR 或 zscore）
        if outlier_method == "iqr":
            rows = self._outlier_iqr(rows, num_cols)
        elif outlier_method == "zscore":
            rows = self._outlier_zscore(rows, num_cols)

        return rows

    # ---- 异常值 ----
    def _outlier_iqr(self, rows: list, num_cols: list) -> list:
        """IQR 法：Q1-1.5*IQR 以下 / Q3+1.5*IQR 以上为异常。

        每列基于原始全量数据独立算界限，收集应删行，最后统一过滤一次——
        避免逐列串行重算导致统计量被上一步删除污染。
        """
        to_drop = set()
        for c in num_cols:
            vals = [float(r[c]) for r in rows if is_num(r.get(c))]
            if len(vals) < 4:
                continue
            q1, q3 = quantile(vals, 0.25), quantile(vals, 0.75)
            iqr = q3 - q1
            if iqr == 0:  # 数据太集中，无异常可判
                continue
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            for idx, r in enumerate(rows):
                if is_num(r.get(c)) and not (lo <= float(r[c]) <= hi):
                    to_drop.add(idx)
        self.report["dropped_outlier"] += len(to_drop)
        return [r for i, r in enumerate(rows) if i not in to_drop]

    def _outlier_zscore(self, rows: list, num_cols: list) -> list:
        for c in num_cols:
            vals = [float(r[c]) for r in rows if is_num(r.get(c))]
            if len(vals) < 3:
                continue
            mean = sum(vals) / len(vals)
            std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 1
            rows = [r for r in rows if not (is_num(r.get(c)) and abs(float(r[c]) - mean) > 3 * std)]
        return rows

    def save(self, rows: list, path: str) -> None:
        """写清洗后数据为 CSV。"""
        if not rows:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


# ═══════════════════════════ 2. stats：数据分析 ═══════════════════════════
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

# ═══════════════════════════ 3. audit：数据审计（盘点/字典/质量/报告）═══════════════════════════
# 对标 pandas-profiling 的数据审视：盘点(列/类型/样本/唯一值) + 字典(字段/口径/枚举)
# + 质量(缺失/重复/异常/类型漂移) + 一键报告。吸收原 web_api.build_report 的数据概览职责。

# 字段中文名 / 计量单位猜测表（启发式：按列名关键词命中）
_FIELD_CN = {
    "id": "编号", "name": "名称", "type": "类型", "status": "状态",
    "temp": "温度", "temperature": "温度", "time": "时间", "date": "日期",
    "power": "功率", "pressure": "压力", "vibration": "振动", "value": "数值",
    "speed": "速度", "humidity": "湿度", "flow": "流量", "count": "数量",
    "qty": "数量", "remark": "备注", "note": "备注", "desc": "描述",
    "location": "位置", "area": "区域", "device": "设备", "sensor": "传感器",
    "voltage": "电压", "current": "电流",
}
_MEASURE = {
    "temp": "温度(℃)", "temperature": "温度(℃)", "temp_c": "温度(℃)",
    "vibration": "振动(mm/s)", "vibration_mm_s": "振动(mm/s)",
    "power": "功率(kW)", "power_kw": "功率(kW)",
    "pressure": "压力(bar)", "pressure_bar": "压力(bar)",
    "humidity": "湿度(%)", "humidity_pct": "湿度(%)",
    "speed": "转速(rpm)", "rpm": "转速(rpm)",
    "voltage": "电压(V)", "current": "电流(A)",
    "flow": "流量", "time": "时间", "date": "日期",
}


def _field_cn(column: str) -> str:
    """列名 → 中文名启发式（下划线/驼峰拆分，常用词映射）。"""
    words = re.split(r"[_\s]+", column.strip())
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", " ".join(w for w in words if w)).split()
    cn = "".join(_FIELD_CN.get(w.lower(), "") for w in words)
    return cn or column


def _field_measure(column: str, type_: str) -> str:
    """列名 → 计量单位猜测。"""
    key = column.lower()
    for k, m in _MEASURE.items():
        if k in key:
            return m
    return {"integer": "数量(个)", "float": "数值", "date": "日期", "text": "文本", "empty": "", "missing": ""}.get(type_, "文本")


def schema(rows: list) -> dict:
    """盘点：列名/类型/非空样本/唯一值数。"""
    if not rows:
        return {"columns": [], "total_rows": 0, "fields": {}}
    total = len(rows)
    fields = {}
    for c in rows[0].keys():
        vals = [str(r.get(c, "")).strip() for r in rows]
        non_empty = [v for v in vals if v]
        fields[c] = {
            "type": guess_type(non_empty[0]) if non_empty else "empty",
            "non_empty": len(non_empty),
            "missing": total - len(non_empty),
            "unique": len(set(vals)),
            "sample": non_empty[:5],
        }
    return {"columns": list(rows[0].keys()), "total_rows": total, "fields": fields}


def dictionary(rows: list) -> dict:
    """字典：字段中文名/口径/枚举值（启发式，确定性）。"""
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
        fields[c] = {
            "name": c,
            "cn": _field_cn(c),
            "measure": _field_measure(c, t),
            "type": t,
            "caliber": f"该字段 {len(non_empty)}/{total} 个非空值，{len(uniq)} 个不同取值",
            "enum": enum,
        }
    return {"columns": list(rows[0].keys()), "total_rows": total, "fields": fields}


def quality(rows: list) -> dict:
    """质量：缺失/重复/异常/类型漂移。返回 {ok, issues, metrics}。"""
    if not rows:
        return {"ok": True, "issues": [], "metrics": {"rows": 0}}
    total = len(rows)
    cols = list(rows[0].keys())
    issues = []

    # 缺失
    missing = {}
    for c in cols:
        m = sum(1 for r in rows if not str(r.get(c, "")).strip())
        if m:
            missing[c] = m
            issues.append({"level": "warn", "type": "missing", "column": c,
                           "count": m, "rate": round(m / total, 3)})

    # 重复
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

    # 类型漂移（首位类型 vs 其余） + 异常值（数值列 IQR）
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
        "ok": len(issues) == 0,
        "total_rows": total,
        "total_cols": len(cols),
        "metrics": {
            "rows": total,
            "missing_total": sum(missing.values()),
            "duplicates": dups,
            "outliers": outlier_total,
        },
        "missing": missing,
        "type_drift": drift,
        "issues": issues,
    }


def _col_stats(rows: list) -> dict:
    """数值列描述统计（供 report 用）。"""
    out = {}
    if not rows:
        return out
    for c in rows[0].keys():
        nums = [float(r[c]) for r in rows if is_num(r.get(c))]
        if nums:
            out[c] = describe(nums)
    return out


def report(rows: list) -> dict:
    """一键全量数据审视报告（盘点 + 字典 + 质量 + 统计 + 预览）。

    对标 pandas-profiling，吸收原 web_api.build_report 的数据概览职责。
    """
    return {
        "schema": schema(rows),
        "dictionary": dictionary(rows),
        "quality": quality(rows),
        "stats": _col_stats(rows),
        "preview": rows[:5],
    }
