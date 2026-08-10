# -*- coding: utf-8 -*-
"""gen.py — 代码生成与工程文档生成（FDE 核心能力）。

方法论：FDE 写代码/写文档 = 个人能力放大。复用 provider 模型分层：
简单生成走本地，复杂生成走远端（可降级）。零依赖。
生成物可选过 code.py 影响分析（改代码前查波及面）。
"""
from __future__ import annotations

from solo import provider as provider_mod


def generate_code(prompt: str, language: str = "python", tier: str = "auto") -> str:
    """生成代码。language 提示语言；tier auto 复杂走远端。"""
    p = provider_mod.Provider.from_config({})
    sys_prompt = (
        f"你是资深工程师。用{language}写代码，遵守：\n"
        "1. 极简原则，不加过度抽象\n"
        "2. 只写必要的，可运行的\n"
        "3. 注释简短，说明意图\n"
        f"任务: {prompt}"
    )
    return p.complete(sys_prompt, tier=tier)


def generate_doc(topic: str, kind: str = "readme", tier: str = "local") -> str:
    """生成工程文档。kind: readme / changelog / docstring / guide。"""
    p = provider_mod.Provider.from_config({})
    templates = {
        "readme": "为以下项目写一个简洁 README（定位/快速开始/能力/限制/致谢）",
        "changelog": "写一个 CHANGELOG 的 0.1.0 段（新增/修复/方法论）",
        "docstring": "为以下代码写 docstring（中文，说明用途/参数/返回）",
        "guide": "写一个使用指南（清晰步骤，面向新人）",
    }
    tpl = templates.get(kind, templates["readme"])
    sys_prompt = f"{tpl}:\n{topic}\n\n遵守：中文，简洁，诚实，不夸大。"
    return p.complete(sys_prompt, tier=tier)


def review_code(code: str, tier: str = "local") -> str:
    """代码审查（FDE 自查）。简单审查本地，深度审查远端。"""
    p = provider_mod.Provider.from_config({})
    sys_prompt = (
        "你是代码审查者。审查以下代码，指出：\n"
        "1. 真实 bug（注入/未用 import/边界）\n"
        "2. 过度工程\n"
        "3. 可改进处\n"
        "只报真实问题，不吹毛求疵。\n\n代码:\n" + code
    )
    return p.complete(sys_prompt, tier=tier)
