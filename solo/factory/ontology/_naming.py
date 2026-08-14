# -*- coding: utf-8 -*-
"""_naming.py — 本体命名/类型判定的模块级工具（无状态，供各 mixin 复用）。

与 factory-ontology-kit 的 csv_to_owl 方法论对齐。NS 前缀 + 列名/类型启发式。
"""
from __future__ import annotations

import re

NS = "http://solo.local/ontology#"


def guess_type(value: str) -> str:
    """启发式猜列类型：整数/浮点/日期/文本。"""
    v = value.strip()
    if re.fullmatch(r"-?\d+", v):
        return "integer"
    if re.fullmatch(r"-?\d+\.\d+", v):
        return "decimal"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return "date"
    return "string"


def local_name(col: str) -> str:
    """列名 → 本体局部名。None 容错。

    保留中文字符（CJK），使中文列名（如"材质"/"规格"）能原样返回，
    而非被全量替换成下划线（修复 P0-2 中文列名损坏）。
    """
    if col is None:
        return "_"
    return re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "_", str(col).strip())
