# -*- coding: utf-8 -*-
"""kernels/__init__.py — 纯算法内核（L1，开源地基）。

全部为无状态纯函数：确定性、无 IO、无网络、可被任何原子独立 import。
不承载有状态类（状态归原子 _impl/），不承载 op 语义，不可被运行时路由。
"""
from __future__ import annotations

__all__ = [
    "spc", "monitor_stats", "forecast", "rules",
    "ontology_core", "memory_score", "survey_core",
]
