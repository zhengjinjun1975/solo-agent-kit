# -*- coding: utf-8 -*-
"""clean.py — 工厂数据清洗（零依赖，标准库）。

方法论（Cleanits + 工业数据预处理最佳实践）：
工厂现场数据（MES/SCADA/传感器）脏、缺、噪，清洗是建模的前提。
能力：缺失值处理 / 去重 / 异常值识别 / 类型推断 / 清洗报告。

对齐 FDE：给工厂现场数据做第一道工序，为 stats 分析和 ontology 建模喂干净数据。
"""
from __future__ import annotations

import csv
import json
import math
import os
import re


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
                                if x.get(c, "").strip() and _isnum(x.get(c))]
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
        """IQR 法：Q1-1.5*IQR 以下 / Q3+1.5*IQR 以上为异常。"""
        out = []
        for c in num_cols:
            vals = [float(r[c]) for r in rows if _isnum(r.get(c))]
            if len(vals) < 4:
                continue
            q1, q3 = _quantile(vals, 0.25), _quantile(vals, 0.75)
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            dropped = 0
            for r in rows:
                if _isnum(r.get(c)) and not (lo <= float(r[c]) <= hi):
                    dropped += 1
            self.report["dropped_outlier"] += dropped
            out = [r for r in rows if not (_isnum(r.get(c)) and not (lo <= float(r[c]) <= hi))]
            rows = out
        return rows

    def _outlier_zscore(self, rows: list, num_cols: list) -> list:
        for c in num_cols:
            vals = [float(r[c]) for r in rows if _isnum(r.get(c))]
            if len(vals) < 3:
                continue
            mean = sum(vals) / len(vals)
            std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals)) or 1
            rows = [r for r in rows if not (_isnum(r.get(c)) and abs(float(r[c]) - mean) > 3 * std)]
        return rows

    def save(self, rows: list, path: str) -> None:
        """写清洗后数据为 CSV。"""
        if not rows:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


def _isnum(v) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def _quantile(vals: list, q: float) -> float:
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo, hi = int(k), int(k) + 1
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
