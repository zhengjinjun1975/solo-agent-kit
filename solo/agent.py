# -*- coding: utf-8 -*-
"""agent.py — 循环五态（感知→记忆装载→推理→行动→记忆提交→输出）。

方法论（VISION §17 + §23）：harness 三支柱 + 可证伪进化预留。
v1：最小闭环——记忆装载 + skill注入 + 本体检索 + 模型推理 + 记忆提交。
零依赖。
"""
from __future__ import annotations

from solo import memory as memory_mod
from solo import provider as provider_mod
from solo import skill as skill_mod


def run(task: str, mem_dir: str = None, skill_dir: str = None) -> dict:
    """循环五态最小实现。返回 {task, suggestion, context}。"""
    # 1. 感知
    m = memory_mod.Memory(mem_dir or memory_mod.DEFAULT_DIR)

    # 2. 记忆装载：热域画像 + 温域相关事实 + skill 注入
    profile = m.profile_text()
    related = m.search(task, top_k=3)
    related_txt = "\n".join(f"- {f['text']}" for f in related)
    sk = skill_mod.Skill(skill_dir or skill_mod.DEFAULT_DIR)
    skill_hint = sk.build_prompt(task)

    # 3. 推理：本地优先，复杂走远端
    context = f"任务: {task}\n\n用户画像:\n{profile}\n\n相关记忆:\n{related_txt}"
    if skill_hint:
        context += f"\n\n适用经验(skill):\n{skill_hint}"
    p = provider_mod.Provider.from_config({})
    text = p.complete(context + "\n\n请给出简洁处理建议(中文):", tier="local")

    # 4. 记忆提交：任务有价值 → 记入事实层
    m.add_fact(task, tags=["task"])

    return {"task": task, "suggestion": text, "memory_dir": m.dir}
