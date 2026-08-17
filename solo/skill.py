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
import re

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

    # ---- 技能自动生成（从经验自动总结，非手动加）----
    def auto_generate(self, memory: "Memory" = None, min_cluster: int = 2,
                      min_len: int = 10) -> dict:
        """从记忆/经验自动提炼技能：识别高频模式 → 自动生成可复用技能。

        规则（零依赖，避免调用 LLM 不稳定）：
          1. 取事实层中带「auto/沉淀」标签的经验（用后自动存下的）
          2. 提取每条经验的主题词（高频实词，取长度≥2 的连续片段）
          3. 主题词出现 ≥ min_cluster 次 → 作为候选技能触发词
          4. 把同主题的若干条经验文本归纳为「执行步骤」→ 自动生成技能
          5. 幂等：同名技能已存在则不覆盖（走 add 版本递增，source=auto）
        返回 {generated: [...], skipped: n}。
        """
        import collections
        # 1) 取记忆经验（全部事实，或带 auto 标签的）
        if memory is None:
            from solo import memory as memory_mod
            memory = memory_mod.Memory()
        facts = memory._load_facts()
        exp = []
        for f in facts:
            t = (f.get("text") or "").strip()
            tags = f.get("tags") or []
            if len(t) >= min_len and ("auto" in tags or "沉淀" in tags or "经验" in tags):
                exp.append(t)
        if not exp:
            return {"generated": [], "skipped": 0, "reason": "暂无自动沉淀经验，先问答/任务让记忆自动积累"}

        # 2) 主题词提取：按常见连接词/标点切分，取长度≥2 的实词片段
        stop = set("的了吗呢和与及在是我想我们你们他们如何怎样什么为什么怎么才能让把被对从到对此关于因为所以但是然后最后"
                   "用于用后自动存自动沉淀经验技能记忆问答审查决策任务完成发现结论做法步骤实践方案问题建议")
        tokens = collections.Counter()
        for t in exp:
            for seg in re.split(r"[,，。；;：:!！?？\s、/()（）\[\]【】]+", t):
                seg = seg.strip()
                if 2 <= len(seg) <= 12 and seg not in stop:
                    tokens[seg] += 1
        # 3) 高频主题词 → 候选技能
        hot = [w for w, c in tokens.items() if c >= min_cluster]
        if not hot:
            return {"generated": [], "skipped": 0, "reason": "暂无高频主题，经验还需更多积累"}

        # 3b) 共享关键词提取：用于技能触发词，让技能能被「部署/清洗/分析」等真实场景词触发
        def _bigrams(t: str):
            return {t[i:i+2] for i in range(len(t) - 1)
                    if t[i:i+2] not in stop
                    and not t[i:i+2].isdigit()
                    and all(c.isalnum() or "\u4e00" <= c <= "\u9fff" for c in t[i:i+2])}

        generated, skipped = [], 0
        for topic in hot[:8]:
            # 该主题关联的经验（含主题词的）作为执行步骤
            steps = [t for t in exp if topic in t][:8]
            if not steps:
                continue
            # 触发词 = 主题词 + 该主题步骤中高频出现的共享关键词
            local_bigram = collections.Counter()
            for st in steps:
                for bg in _bigrams(st):
                    local_bigram[bg] += 1
            shared = [w for w, c in local_bigram.items()
                      if c >= 2 and w not in stop][:4]
            trigger = [topic] + shared
            name = f"经验·{topic}"
            old = self.get(name)
            # 幂等：同名且同步骤的同源 auto 技能已存在 → 跳过，不重复生成/不盲目升级版本
            if old and old.get("source") == "auto" and old.get("steps") == steps:
                skipped += 1
                continue
            skill = self.add(name, trigger=trigger, steps=steps, source="auto")
            generated.append({"name": name, "trigger": skill["trigger"],
                              "steps_count": len(steps), "version": skill["version"],
                              "auto": True})
        return {"generated": generated, "skipped": skipped}


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
