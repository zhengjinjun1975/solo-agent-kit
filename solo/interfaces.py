# -*- coding: utf-8 -*-
"""interfaces.py — 统一接口契约（P1-1）。

用 dataclass 定义模块间返回模型，替代裸 dict，提升类型安全与可维护性。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DescribeResult:
    """单列描述统计结果。"""
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    min: float = 0.0
    max: float = 0.0
    p25: float = 0.0
    p75: float = 0.0
    count: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class CleanReport:
    """数据清洗报告。"""
    input_rows: int = 0
    output_rows: int = 0
    dropped_dup: int = 0
    dropped_outlier: int = 0
    filled_missing: int = 0
    types: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class AgentResult:
    """Agent 执行结果统一契约。"""
    intent: str = ""
    ok: bool = True
    message: str = ""
    data: Any = None
    tier: str = "local"
    conversation_id: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"intent": self.intent, "ok": self.ok, "message": self.message,
             "tier": self.tier}
        if self.data is not None:
            d["data"] = self.data
        if self.conversation_id:
            d["conversation_id"] = self.conversation_id
        return d
