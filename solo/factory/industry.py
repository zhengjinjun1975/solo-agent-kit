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
import re

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

# ═══ 当前行业持久化状态（改行业→自动重建的事件驱动核心）═══
# 只要"当前行业"被设置，任何省略 industry 的下游起草/决策都会自动跟随它，
# 从而杜绝"改行业后仍旧行业产物"的串台死角（镜像 factory-ontology 改行业→自动建模）。
# 测试可 monkeypatch _STATE_FILE 指向临时文件以隔离真实用户状态。
_STATE_FILE = os.path.join(os.path.expanduser("~"), ".solo", "current_industry.json")


def get_current_industry() -> str:
    """读"当前行业"持久化状态。未设置/文件缺失/损坏 → None（默认工厂）。"""
    try:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, encoding="utf-8") as f:
                v = json.load(f).get("industry")
            return str(v).strip() or None if v is not None else None
    except (OSError, json.JSONDecodeError):
        pass
    return None


def set_current_industry(industry: str = None) -> str:
    """设置"当前行业"（持久化，改行业事件）。industry 为空 → 复位到默认工厂。

    返回生效的行业显示名（"(默认工厂)" 表示已复位/未登记兜底）。
    """
    industry = (industry or "").strip() or None
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"industry": industry}, f, ensure_ascii=False)
    except OSError:  # 写失败不阻断（读不到就当默认）
        pass
    return industry or "(默认工厂)"


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

    industry 为空 → 跟随"当前行业"状态（若已设置）；否则默认工厂，保证向后兼容。
    这是改行业→自动联动的单一决策点：任何省略 industry 的下游起草/决策
    （问题集/词典/报告/决策）都会自动用当前行业配置，杜绝"改行业仍旧行业产物"。
    """
    if not industry or not str(industry).strip():
        cur = get_current_industry()
        if cur:
            return _resolve(str(cur).strip())
        return copy.deepcopy(_resolve(""))  # 无当前行业 → 默认工厂
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
    未显式指定行业 → 跟随"当前行业"状态（改行业自动联动）。
    """
    raw = (industry or "").strip() or None
    effective = raw or get_current_industry()
    cfg = load_industry(raw)   # raw 为空时内部已跟随当前行业
    reg = load_industries()
    known = effective is not None and effective in (reg.get("industries") or {})
    return {
        "industry": effective or "(默认工厂)",
        "kb": cfg["kb"],
        "entity_cn": cfg["entity_cn"],
        "measure": cfg["measure"],
        "col_cn": dict(cfg.get("col_cn", {})),
        "thresholds": dict(cfg.get("_thresholds", {})),
        "note": (reg.get("industries") or {}).get(effective, {}).get("note", ""),
        "known": known,
    }


def industries_list() -> list:
    """列出已登记行业（含名称/默认kb/实体）。"""
    reg = load_industries()
    return [
        {"industry": name,
         "kb": entry.get("kb", reg.get("_defaults", {}).get("kb", _FALLBACK["kb"])),
         "entity_cn": entry.get("entity_cn", reg.get("_defaults", {}).get("entity_cn", _FALLBACK["entity_cn"])),
         "measure": entry.get("measure", reg.get("_defaults", {}).get("measure", _FALLBACK["measure"])),
         "note": entry.get("note", "")}
        for name, entry in (reg.get("industries") or {}).items()
    ]


def rebuild_industry_artifacts(industry: str = None, rows: list = None, table_name: str = None,
                               out_dir: str = None, questions_n: int = 12, **report_kw) -> dict:
    """【改行业→自动重建产物】事件驱动入口（镜像 factory-ontology 的"改行业→自动建模"）。

    一次调用完成"改行业"的全部级联副作用：
      1. 持久化"当前行业"（set_current_industry）—— 之后任何省略 industry 的
         下游起草/决策（问题集/词典/报告/决策）都自动跟随新行业，不串台。
      2. 自动重建 FDE 全部产物：
           D0 问题集    draft_questions（行业实体/量词/列名中文）
           D1 词典      lexicon_draft + to_factory_lexicon（行业 entity/col_cn → 工厂契约）
           D4 报告      report_draft_dict（行业 → kb 自动解析）
           决策阈值      thresholds（行业 _thresholds 覆盖全局）
      3. 按"行业+kb"隔离持久化产物包到 out_dir（跨行业不互相覆盖/串台）。

    参数:
      industry: 目标行业名。为空 → 复位默认工厂。
      rows: 数据行（list[dict]）。给出行集/词典才重建；否则只重建报告/阈值。
      table_name: 词典的 table 名（默认用行业 kb）。
      out_dir: 产物包持久化目录（默认 None 不落盘）。
      questions_n: 问题集上限。
      **report_kw: report_draft_dict 透传（hit/questions_n/hits/asset_versions/health/baseline/note）。

    返回 {"industry", "kb", "entity_cn", "measure", "thresholds", "artifacts", "persisted"}。
    """
    from .assist import (draft_questions, lexicon_draft, to_factory_lexicon,
                         to_review_items, report_draft_dict)
    cfg = apply_industry(industry)
    # 1. 事件副作用：持久化当前行业（改行业核心）
    set_current_industry(industry)
    artifacts = {}
    if rows:
        headers = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
        artifacts["questions"] = draft_questions(rows, industry=industry, limit=questions_n)
        lex = lexicon_draft(headers, rows[:30], industry=industry)
        artifacts["lexicon"] = lex
        artifacts["factory_lexicon"] = to_factory_lexicon(
            lex, table_name=(table_name or cfg["kb"]), industry=industry)
        # 闭源 review 队列（P2 接线：改行业即带上待确认项，供 ingest_lexicon 消费）
        artifacts["review_items"] = to_review_items(lex)
    # 报告草稿（D4，行业 → kb 自动解析）
    report_defaults = {"hit": 0.0, "questions_n": questions_n, "hits": 0}
    report_defaults.update(report_kw)
    artifacts["report"] = report_draft_dict(industry=industry, **report_defaults)
    # 决策产物 = 该行业生效阈值（覆盖全局）
    artifacts["thresholds"] = cfg["thresholds"]
    # 3. 按"行业+kb"隔离持久化（跨行业不串台）
    persisted = {}
    if out_dir:
        import json as _json
        os.makedirs(out_dir, exist_ok=True)
        base = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "_", cfg["industry"])
        base = f"{cfg['kb']}_{base}"
        for key, val in artifacts.items():
            if not val:
                continue
            p = os.path.join(out_dir, f"{base}_{key}.json")
            with open(p, "w", encoding="utf-8") as f:
                _json.dump(val, f, ensure_ascii=False, indent=2)
            persisted[key] = p
    return {"industry": cfg["industry"], "kb": cfg["kb"], "entity_cn": cfg["entity_cn"],
            "measure": cfg["measure"], "thresholds": cfg["thresholds"],
            "artifacts": artifacts, "persisted": persisted}
