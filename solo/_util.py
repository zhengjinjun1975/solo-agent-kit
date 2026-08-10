# -*- coding: utf-8 -*-
"""_util.py — solo 内部极简通用工具（消除跨模块重复）。

极简原则: stats/clean/ontology/web_api 各自重复实现 is_num/quantile,
统一放这里, 各模块 import, 保持零依赖独立(不从 domain-libs 拉取)。
从原子库(D:/domain-libs/solo-atoms/stats.py)复制极简版, 保持实现一致。
"""
from __future__ import annotations


def is_num(v) -> bool:
    """判断值能否转 float。"""
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def quantile(vals: list, q: float) -> float:
    """线性插值分位数(与原子库 stats._quantile 一致)。"""
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo, hi = int(k), int(k) + 1
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
