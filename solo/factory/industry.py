# -*- coding: utf-8 -*-
"""industry.py — 行业→kb/词典联动 数据驱动注册表加载器（FDE 交付辅助）。

对齐 product-system-closed-loop：solo 的「行业」应是数据驱动的第一类公民——
一个行业对应一个 知识库(kb) + 默认词典实体 + 量词 + 行业列名中文映射 + 决策阈值覆盖。
改 config/industries.json 即可定义新行业，零 Python（与 decisions.json 同哲学）。

能力：
- load_industries: 读取整个注册表（含默认值兜底）
- load_industry:  解析单个行业 → 合并默认值后的完整配置 dict
- apply_industry: 行业变更的「联动」入口，返回该行业影响到的全部相关产物配置
  （kb / entity_cn / measure / col_cn / decisions 阈值覆盖），
  供上游把行业变更级联到 问题集/词典/报告/决策 的起草。
- industries_list: 列出已注册行业（供 CLI industry-list）

零依赖，纯标准库。未知行业回退默认值（不报错，便于新行业先跑后登记）。
"""
from __future__ import annotations

import copy
import json
import os

# config/industries.json（与 decisions.json 同目录，模式一致）
_CONFIG = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "industries.json"))

# 内置兜底（配置文件缺失时也能工作；与注册表 _defaults 一致）
_FALLBACK = {
    "kb": "factory",
    "entity_cn": "设备",
    "measure": "台",
    "col_cn": {},
    "_thresholds": {},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """深合并 override 到 base 的副本上（dict 递归，list/标量直接替换）。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_industries() -> dict:
    """读取整个注册表。返回 {industries: {行业: 配置}, _defaults: {...}}。"""
    if not os.path.exists(_CONFIG):
        return {"industries": {}, "_defaults": _FALLBACK}
    try:
        with open(_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"industries": {}, "_defaults": _FALLBACK}


def _resolve(industry: str) -> dict:
    """解析单个行业，合并默认值。未知行业 → 仅默认值（不报错）。"""
    reg = load_industries()
    defaults = reg.get("_defaults", _FALLBACK)
    entry = (reg.get("industries") or {}).get(industry, {})
    merged = _deep_merge(defaults, entry)
    merged.setdefault("kb", defaults.get("kb", _FALLBACK["kb"]))
    merged.setdefault("entity_cn", defaults.get("entity_cn", _FALLBACK["entity_cn"]))
    merged.setdefault("measure", defaults.get("measure", _FALLBACK["measure"]))
    merged.setdefault("col_cn", {})
    merged.setdefault("_thresholds", {})
    return merged


def load_industry(industry: str = None) -> dict:
    """返回单个行业的合并配置（含 kb/entity_cn/measure/col_cn/_thresholds）。

    industry 为空 → 返回纯默认值（通用工厂），保证向后兼容。
    """
    if not industry or not str(industry).strip():
        return copy.deepcopy(_resolve(""))  # 空名 → 默认
    return _resolve(str(industry).strip())


def apply_industry(industry: str = None) -> dict:
    """行业变更联动入口：返回该行业影响到的全部相关产物配置。

    调用方据此把行业变更级联到：
      - D0 问题集    → entity_cn / measure
      - D1 词典      → entity_cn / col_cn（行业列名中文映射）
      - D4 报告      → kb / industry（默认 kb 自动解析）
      - 决策规则      → _thresholds（覆盖全局阈值）
    返回 {"industry", "kb", "entity_cn", "measure", "col_cn", "thresholds",
          "note", "known"}。known=False 表示未登记，用默认值兜底。
    """
    industry = (industry or "").strip() or None
    cfg = load_industry(industry)
    reg = load_industries()
    known = industry is not None and industry in (reg.get("industries") or {})
    return {
        "industry": industry or "(默认工厂)",
        "kb": cfg["kb"],
        "entity_cn": cfg["entity_cn"],
        "measure": cfg["measure"],
        "col_cn": dict(cfg.get("col_cn", {})),
        "thresholds": dict(cfg.get("_thresholds", {})),
        "note": (reg.get("industries") or {}).get(industry, {}).get("note", ""),
        "known": known,
    }


def industries_list() -> list:
    """列出已注册行业（含名称/默认kb/实体）。"""
    reg = load_industries()
    return [
        {"industry": name,
         "kb": entry.get("kb", reg.get("_defaults", {}).get("kb", _FALLBACK["kb"])),
         "entity_cn": entry.get("entity_cn", reg.get("_defaults", {}).get("entity_cn", _FALLBACK["entity_cn"])),
         "measure": entry.get("measure", reg.get("_defaults", {}).get("measure", _FALLBACK["measure"])),
         "note": entry.get("note", "")}
        for name, entry in (reg.get("industries") or {}).items()
    ]
