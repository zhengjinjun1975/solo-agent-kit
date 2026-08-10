# -*- coding: utf-8 -*-
"""plugins — 外部插件体系（零第三方依赖，可降级）。

每个插件声明：名称/能力/依赖/是否可用。
list_plugins() 显示可用性（对齐 setup 检查）。
插件不可用时明确降级，不崩溃。

已实现：
  obsidian.py    Obsidian 知识库集成（报告归档/检索/经验沉淀）
  visualize.py   matplotlib 可视化（SPC控制图/趋势/异常标记）
"""
from __future__ import annotations

import importlib


# 插件注册表：名称 -> (模块, 依赖包, 能力描述)
_REGISTRY = {
    "obsidian": {
        "module": "solo.plugins.obsidian",
        "dep": "",                 # 零依赖（文件系统读写）
        "desc": "Obsidian 知识库集成：报告归档/检索/经验沉淀",
    },
    "visualize": {
        "module": "solo.plugins.visualize",
        "dep": "matplotlib",       # 本机已装
        "desc": "数据可视化：SPC控制图/趋势图/异常标记",
    },
    "excel_report": {
        "module": "solo.plugins.excel_report",
        "dep": "openpyxl",         # 本机已装
        "desc": "Excel交付报告：清洗/分析/本体导出",
    },
    "netscan": {
        "module": "solo.plugins.netscan",
        "dep": "",                 # 零依赖
        "desc": "局域网设备扫描：主机存活/端口/服务识别",
    },
}


def _available(mod: str, dep: str) -> bool:
    """判断插件是否可用：模块可导入 + 依赖包可导入。"""
    if dep:
        try:
            importlib.import_module(dep)
        except ImportError:
            return False
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def list_plugins() -> list:
    """列出全部插件及可用性。"""
    out = []
    for name, meta in _REGISTRY.items():
        ok = _available(meta["module"], meta["dep"])
        out.append({
            "name": name,
            "desc": meta["desc"],
            "dep": meta["dep"] or "stdlib",
            "available": ok,
        })
    return out


def get(name: str):
    """加载插件模块。不可用时返回 None（不崩溃）。"""
    meta = _REGISTRY.get(name)
    if not meta:
        return None
    if not _available(meta["module"], meta["dep"]):
        return None
    return importlib.import_module(meta["module"])
