# -*- coding: utf-8 -*-
"""registry.py — 能力注册表（P1-3 开闭原则）。

用 @capability 装饰器注册各能力，agent/cli/web 从注册表动态生成路由与能力清单。
新增一项能力只需注册一次，不再同步改三处。
"""
from __future__ import annotations

# 能力注册表：name -> {suite, desc, handler, enabled}
_CAPABILITIES = {}


def capability(name: str, suite: str = "personal", desc: str = ""):
    """能力注册装饰器。

    用法：
        @capability("clean", "factory", "数据清洗")
        def clean_handler(task, **kw): ...
    """
    def deco(fn):
        _CAPABILITIES[name] = {
            "suite": suite,
            "desc": desc,
            "handler": fn,
            "enabled": True,
        }
        return fn
    return deco


def get_capability(name: str) -> dict:
    return _CAPABILITIES.get(name)


def capabilities() -> dict:
    """按套件分组的公开能力清单（无 handler，供 web 返回）。"""
    out = {"factory": {}, "personal": {}}
    for name, meta in _CAPABILITIES.items():
        out[meta["suite"]][name] = {"desc": meta["desc"], "enabled": meta["enabled"]}
    return out


def all_capabilities() -> dict:
    """完整注册表（含 handler，供内部调度）。"""
    return _CAPABILITIES


# ---- 初始化注册现有能力（避免空清单，handler 由调度方注入）----
def _init_defaults():
    # 只注册元数据（name/suite/desc），handler 由调用方填充，避免循环导入
    for name, suite, desc in [
        ("clean", "factory", "数据清洗（缺失/重复/异常值）"),
        ("stats", "factory", "数据分析（描述/趋势/SPC）"),
        ("ontology", "factory", "本体建模（设备/工单关系）"),
        ("memory", "personal", "三层两域记忆"),
        ("skill", "personal", "可复用经验提取"),
        ("writing", "personal", "六维写作检查"),
        ("code", "personal", "代码生成/审查/库理解"),
    ]:
        capability(name, suite, desc)(lambda t, **k: None)


_init_defaults()
