# -*- coding: utf-8 -*-
"""memory.py — 三层两域记忆（零依赖，独立为主，Obsidian 接口兼容）。

方法论（VISION §6.6 / §22）：
- 热域·画像层：高频关键（每轮注入）
- 温域·事实层：散点事实/决策（语义检索取）
- 温域·场景层：项目完整上下文（整包恢复）
- 冷域·会话层：留底（自动）

独立运行零依赖；数据在单一目录。可选与 Obsidian 通过 Markdown 互通。
"""
from __future__ import annotations

import json
import os
import hashlib

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".solo", "memory")


class Memory:
    """三层两域记忆存储。所有数据在 mem_dir 下，文件格式可移植。

    目录结构：
        mem_dir/
            profile.json       热域·画像层（key: 事实）
            facts.json         温域·事实层（list: {text, tags, ts}）
            scenarios/         温域·场景层（每项目一个 .json）
            sessions/          冷域·会话层（留底）
    """

    def __init__(self, mem_dir: str = DEFAULT_DIR):
        self.dir = mem_dir
        os.makedirs(os.path.join(mem_dir, "scenarios"), exist_ok=True)
        os.makedirs(os.path.join(mem_dir, "sessions"), exist_ok=True)
        self._facts_path = os.path.join(mem_dir, "facts.json")
        self._profile_path = os.path.join(mem_dir, "profile.json")

    # ---- 热域·画像层 ----
    def set_profile(self, key: str, value: str) -> None:
        """画像层：高频关键事实，覆盖旧值。"""
        p = self._load(self._profile_path, {})
        p[key] = value
        self._save(self._profile_path, p)

    def get_profile(self, key: str = None):
        p = self._load(self._profile_path, {})
        return p if key is None else p.get(key)

    def profile_text(self) -> str:
        """画像层全文（每轮注入用）。"""
        p = self._load(self._profile_path, {})
        return "\n".join(f"{k}: {v}" for k, v in p.items())

    # ---- 温域·事实层 ----
    def add_fact(self, text: str, tags: list = None) -> bool:
        """事实层：有价值的都写。返回是否新增（去重）。"""
        facts = self._load(self._facts_path, [])
        h = self._hash(text)
        if any(f.get("h") == h for f in facts):
            return False
        facts.append({"text": text, "tags": tags or [], "h": h, "ts": _now()})
        self._save(self._facts_path, facts)
        return True

    def search(self, query: str, top_k: int = 5, semantic: bool = True):
        """事实层检索。优先 embed 向量（P1-5），无 embed 回退词重叠。"""
        facts = self._load(self._facts_path, [])
        if semantic:
            q_emb = self._try_embed(query)
            if q_emb is not None:
                # 批量向量化一次，避免重复 embed 调用
                vecs = {}
                for f in facts:
                    v = self._try_embed(f["text"])
                    if v:
                        vecs[f.get("h", id(f))] = v
                scored = sorted(
                    facts,
                    key=lambda f: _cosine(q_emb, vecs.get(f.get("h", id(f)), [])),
                    reverse=True)
            else:
                scored = sorted(facts, key=lambda f: _overlap(f["text"], query), reverse=True)
        else:
            scored = facts
        return scored[:top_k]

    def _try_embed(self, text: str):
        """尝试用配置的 embed 模型向量化。失败返回 None（回退词重叠）。"""
        try:
            from solo import provider as provider_mod
            p = provider_mod.Provider.from_file()
            return p.embed(text)
        except Exception:
            return None

    # ---- 温域·场景层 ----
    def set_scenario(self, name: str, content: str) -> None:
        """场景层：项目完整上下文（整包恢复）。"""
        self._save(os.path.join(self.dir, "scenarios", f"{name}.json"),
                   {"name": name, "content": content, "ts": _now()})

    def get_scenario(self, name: str) -> str:
        d = self._load(os.path.join(self.dir, "scenarios", f"{name}.json"), None)
        return d.get("content", "") if d else ""

    def list_scenarios(self) -> list:
        out = []
        d = os.path.join(self.dir, "scenarios")
        for f in os.listdir(d):
            if f.endswith(".json"):
                out.append(f[:-5])
        return out

    # ---- 冷域·会话层 ----
    def log_session(self, name: str, content: str) -> None:
        self._save(os.path.join(self.dir, "sessions", f"{name}.json"),
                   {"name": name, "content": content, "ts": _now()})

    # ---- Obsidian 互通 ----
    def import_markdown(self, path: str) -> int:
        """导入一个 Markdown 文件为事实层。返回新增条数。"""
        if not os.path.isdir(path):
            return 0
        added = 0
        for root, _, files in os.walk(path):
            for f in files:
                if f.endswith(".md"):
                    try:
                        with open(os.path.join(root, f), encoding="utf-8", errors="ignore") as fh:
                            for line in fh:
                                line = line.strip()
                                if 8 <= len(line) <= 280:
                                    if self.add_fact(line):
                                        added += 1
                    except Exception:
                        continue
        return added

    def export_markdown(self, out_dir: str) -> None:
        """导出事实层为 Markdown（可回写 Obsidian）。"""
        os.makedirs(out_dir, exist_ok=True)
        facts = self._load(self._facts_path, [])
        with open(os.path.join(out_dir, "solo-memory.md"), "w", encoding="utf-8") as fh:
            for f in facts:
                fh.write("- " + f["text"] + "\n")

    # ---- OptMem 互通(可选增强): 把经验/方法论沉淀进 OptMem 全局记忆 ----
    def optmem_note(self, text: str):
        """调 E:\\optmem\\memo note 沉淀一条全局记忆(经验/方法论)。

        用于 FDE 工具箱经验/方法论跨项目、跨会话复用。失败静默返回, 不打断主流程。
        """
        return optmem_note(text)

    def optmem_search(self, query: str, top_k: int = 5):
        """调 E:\\optmem\\memo_search.py 语义检索 OptMem 记忆。返回匹配文本列表。"""
        return optmem_search(query, top_k)

    # ---- 内部 ----
    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _load(path: str, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def _save(path: str, data) -> None:
        from solo.base import atomic_write, lock_for
        with lock_for(path):
            atomic_write(path, data)


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _overlap(a: str, b: str) -> float:
    """零依赖语义打分：字符 bigram 重叠率（简单但有效，避免引向量库）。"""
    a_b = {a[i:i+2] for i in range(len(a) - 1)}
    b_b = {b[i:i+2] for i in range(len(b) - 1)}
    if not b_b:
        return 0.0
    return len(a_b & b_b) / len(b_b)


def _cosine(a: list, b: list) -> float:
    """余弦相似度（embed 向量检索）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


# ------------------------------------------------------------------ OptMem 互通（可选增强，零依赖）
# 把 FDE 工具箱经验/方法论沉淀进 OptMem 全局记忆（E:\optmem），跨项目、跨会话复用。
# 失败静默返回，绝不打断主流程；可用环境变量 OPTMEM_NOTE=0 关闭。
_MEMO = os.environ.get("OPTMEM_MEMO", r"E:\optmem\memo")
_MEMO_SEARCH = os.environ.get("OPTMEM_MEMO_SEARCH", r"E:\optmem\memo_search.py")
_MEMORY_DIR = os.environ.get("OPTMEM_MEMORY_DIR", r"E:\optmem\memory")
_OPTMEM_ENABLED = os.environ.get("OPTMEM_NOTE", "1").lower() not in ("0", "false", "no", "off")


def optmem_note(text: str):
    """调 E:\optmem\memo note 沉淀一条全局记忆。返回 (ok, 消息)。"""
    if not _OPTMEM_ENABLED:
        return False, "disabled(OPTMEM_NOTE=0)"
    import subprocess
    import sys as _sys
    line = text.encode("utf-8")[:280].decode("utf-8", errors="ignore")
    env = dict(os.environ)
    env["MEMORY_DIR"] = _MEMORY_DIR
    try:
        r = subprocess.run(
            [_sys.executable, _MEMO, "note", line],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
        if r.returncode == 0:
            first = (r.stdout or r.stderr or "").strip().splitlines()
            return True, (first[0] if first else "ok")
        return False, (r.stderr or r.stdout or "").strip()
    except Exception as e:
        return False, f"optmem 不可用: {e}"


def optmem_search(query: str, top_k: int = 5):
    """调 E:\optmem\memo_search.py 语义检索 OptMem 记忆。失败返回 []。"""
    if not _OPTMEM_ENABLED:
        return []
    import subprocess
    import sys as _sys
    env = dict(os.environ)
    env["MEMORY_DIR"] = _MEMORY_DIR
    try:
        r = subprocess.run(
            [_sys.executable, _MEMO_SEARCH, query, str(top_k)],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)
        if r.returncode == 0:
            return [ln for ln in r.stdout.splitlines() if ln.strip()]
        return []
    except Exception:
        return []


if __name__ == "__main__":
    # 自检: 沉淀一条示例方法论并检索回看（可用 OPTMEM_NOTE=0 跳过）。
    ok, msg = optmem_note("Solo FDE 工具箱: 交付前先跑 e2e 联调再打补丁, 避免返工")
    print("note:", ok, msg)
