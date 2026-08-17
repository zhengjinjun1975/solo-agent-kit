# -*- coding: utf-8 -*-
"""_impl/memory_store.py — Memory 有状态存储（画像/情景/事实/OptMem）。

状态在原子 _impl/，纯检索打分来自 kernels.memory_score。
"""
from __future__ import annotations

import json
import os


class MemoryStore:
    """三层两域记忆 + OptMem 文件存储。"""

    def __init__(self, dir):
        self.dir = dir or os.path.join(os.path.expanduser("~"), ".solo", "memory")
        os.makedirs(self.dir, exist_ok=True)
        self._facts_path = os.path.join(self.dir, "facts.json")
        self._profile_path = os.path.join(self.dir, "profile.json")
        self._optmem_path = os.path.join(self.dir, "optmem.json")

    def _load(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return default
        return default

    def _save(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 画像 ----
    def set_profile(self, key, value):
        p = self._load(self._profile_path, {})
        p[key] = value
        self._save(self._profile_path, p)
        return p

    def profile(self):
        return self._load(self._profile_path, {})

    # ---- 情景 ----
    def set_scenario(self, name, content):
        s = self._load(self._scenario_path(), {})
        s[name] = content
        self._save(self._scenario_path(), s)
        return s

    def _scenario_path(self):
        return os.path.join(self.dir, "scenarios.json")

    def scenarios(self):
        return self._load(self._scenario_path(), {})

    # ---- 事实 ----
    def add_fact(self, text, tags=None):
        if not text or not str(text).strip():
            return False
        from kernels.memory_score import _hash
        facts = self._facts()
        h = _hash(text)
        if any(f.get("h") == h for f in facts):
            return False
        facts.append({"text": text, "tags": tags or [], "h": h})
        self._save(self._facts_path, facts)
        return True

    def _facts(self):
        return self._load(self._facts_path, [])

    def facts(self):
        return self._facts()

    def update_fact(self, h, new_text, tags=None):
        facts = self._facts()
        for f in facts:
            if f.get("h") == h:
                f["text"] = new_text
                if tags:
                    f["tags"] = sorted(set((f.get("tags") or []) + tags))
                break
        self._save(self._facts_path, facts)
        return facts

    def delete_fact(self, h):
        facts = [f for f in self._facts() if f.get("h") != h]
        self._save(self._facts_path, facts)
        return facts

    # ---- OptMem ----
    def optmem_note(self, text):
        notes = self._load(self._optmem_path, [])
        notes.append({"text": text})
        self._save(self._optmem_path, notes)
        return len(notes)

    def optmem_notes(self):
        return self._load(self._optmem_path, [])
