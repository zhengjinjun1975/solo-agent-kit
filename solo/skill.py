# -*- coding: utf-8 -*-
"""skill.py — 可复用经验提取（跨轨迹抽象，浅层）。

方法论（ACL2026 记忆综述 + Burin）：学到新东西就写 skill（代码不是笔记）。
跨轨迹抽象三层粒度——本模块实现"浅层"：自然语言规则 + 触发边界 + 版本。
v2 升级为"中层"：skill 是代码骨架。

零依赖：经验存 JSON 文件，带触发词/版本/步骤。
"""
from __future__ import annotations

import json
import os

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".solo", "skills")


class Skill:
    """可复用经验封装。每 skill：name / trigger / steps / version / source。"""

    def __init__(self, dir: str = DEFAULT_DIR):
        self.dir = dir
        os.makedirs(dir, exist_ok=True)
        self._index_path = os.path.join(dir, "index.json")

    def add(self, name: str, trigger: list, steps: list, source: str = "") -> dict:
        """新增 skill。trigger = 触发词/场景列表；steps = 执行步骤。返回 skill。"""
        idx = self._load_index()
        ver = idx.get(name, {}).get("version", 0) + 1
        skill = {
            "name": name,
            "trigger": trigger,
            "steps": steps,
            "source": source,
            "version": ver,
            "ts": _now(),
        }
        idx[name] = skill
        self._save_index(idx)
        return skill

    def get(self, name: str) -> dict:
        return self._load_index().get(name)

    def list(self) -> list:
        return sorted(self._load_index().keys())

    def all_details(self) -> list:
        """返回全部技能的完整信息（供列表式展示）。"""
        idx = self._load_index()
        # 过滤乱码技能(含 U+FFFD 替换字符 = 写入时编码损坏, 无法恢复)
        return [idx[name] for name in sorted(idx.keys())
                if "\ufffd" not in name and "\ufffd" not in str(idx[name])]

    def match(self, text: str) -> list:
        """按触发词匹配当前任务的适用 skill（按触发词命中排序）。"""
        idx = self._load_index()
        t = text.lower()
        hits = []
        for name, s in idx.items():
            score = sum(1 for tr in s.get("trigger", []) if tr.lower() in t)
            if score:
                hits.append((score, name))
        hits.sort(reverse=True)
        return [name for _, name in hits]

    def build_prompt(self, text: str) -> str:
        """把匹配的 skill 步骤注入 prompt（agent 上下文用）。"""
        matched = self.match(text)
        if not matched:
            return ""
        parts = []
        for name in matched[:3]:
            s = self.get(name)
            steps = "\n".join(f"  {i+1}. {st}" for i, st in enumerate(s["steps"]))
            parts.append(f"[skill:{name}] v{s['version']}\n{steps}")
        return "\n\n".join(parts)

    # ---- 内部 ----
    def _load_index(self) -> dict:
        if not os.path.exists(self._index_path):
            return {}
        try:
            with open(self._index_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_index(self, idx: dict) -> None:
        from solo.base import atomic_write, lock_for
        with lock_for(self._index_path):
            atomic_write(self._index_path, idx)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")
