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
import re

from solo.base import lock_for

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
        # P1 性能优化：事实层改为「追加日志 + 内存缓存」增量写，避免每次全量 load+save(O(n²))
        self._journal_path = os.path.join(mem_dir, "facts.jsonl")
        self._facts_cache = None   # 懒加载：facts.json(快照) + facts.jsonl(增量) 合并后的完整列表
        self._hash_cache = None    # 去重哈希集合
        self._emb_cache = {}       # search embed 向量缓存 h→vec，避免重复 embed 调用

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
    def _load_facts(self) -> list:
        """懒加载事实层：facts.json(快照) + facts.jsonl(追加日志) 合并为完整列表。

        首次调用后缓存在 _facts_cache，之后 O(1) 返回，避免每次全量读文件。
        """
        if self._facts_cache is not None:
            return self._facts_cache
        facts = self._load(self._facts_path, [])
        if os.path.exists(self._journal_path):
            with lock_for(self._journal_path):
                with open(self._journal_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            facts.append(json.loads(line))
                        except Exception:
                            continue
        self._facts_cache = facts
        self._hash_cache = {f.get("h") for f in facts}
        return facts

    def _consolidate(self, facts: list = None) -> list:
        """把内存缓存合并写回 facts.json 快照，并清空追加日志。

        仅在增删改 / 读后落盘时调用（O(n) 一次），add_fact 热路径不触发，避免 O(n²)。
        """
        facts = self._facts_cache if facts is None else facts
        self._save(self._facts_path, facts)
        self._facts_cache = facts
        self._hash_cache = {f.get("h") for f in facts}
        if os.path.exists(self._journal_path):
            with lock_for(self._journal_path):
                with open(self._journal_path, "w", encoding="utf-8") as f:
                    f.truncate()
        return facts

    def _maybe_consolidate(self):
        """日志非空时才合并落盘（读操作后保持 facts.json 新鲜，成本摊薄）。"""
        if self._facts_cache is not None and os.path.exists(self._journal_path):
            try:
                if os.path.getsize(self._journal_path) > 0:
                    self._consolidate()
            except OSError:
                pass

    def add_fact(self, text: str, tags: list = None) -> bool:
        """事实层：有价值的都写。返回是否新增（去重）。

        P1 性能优化：增量追加写入 facts.jsonl（O(1)），不每次全量 load+save 整个列表，
        使 3000 条批量写入从 O(n²) 降到近线性。
        """
        if not isinstance(text, str) or not text.strip():
            return False
        facts = self._load_facts()
        h = self._hash(text)
        if self._hash_cache is not None and h in self._hash_cache:
            return False
        rec = {"text": text, "tags": tags or [], "h": h, "ts": _now()}
        facts.append(rec)
        if self._hash_cache is not None:
            self._hash_cache.add(h)
        with lock_for(self._journal_path):
            with open(self._journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True

    # ---- 写入决策层（P0：对齐 Mem0 决策循环 ADD/UPDATE/DELETE，需自实现）----
    def write(self, text: str, tags: list = None, threshold: float = 0.6) -> dict:
        """记忆写入决策层：写入前召回相似旧记忆，规则判定 ADD/UPDATE/SKIP。

        借鉴 Mem0 论文「写入前召回相似 + 决策层」：避免日期戳/标题变体重复堆积。
        零依赖自实现（不引第三方 SDK）：
          1. 召回 top-k 相似旧事实（复用 search 语义/词重叠）
          2. 相似度 ≥ 0.9 → SKIP（等价，跳过）
          3. 相似度 ≥ threshold → UPDATE（同主题，覆盖旧值，保留时序）
          4. 否则 → ADD（新事实）
        返回 {action, reason, fact, similar}，落库带 updated 时间戳。
        """
        facts = self._load_facts()
        # 1) 召回相似旧记忆（词重叠打分，零依赖）
        scored = []
        for f in facts:
            sim = _overlap(text, f["text"])
            if sim >= 0.3:
                scored.append((sim, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        similar = [f for s, f in scored[:5]]

        # 2) 决策
        if similar and scored[0][0] >= 0.9:
            return {"action": "SKIP", "reason": "与现有记忆等价(相似度≥0.9)，跳过防重复",
                    "text": text, "similar": similar, "updated": False}
        if similar and scored[0][0] >= threshold:
            top = similar[0]
            # UPDATE：保留原 text 主体，追加新视角（避免信息丢失），更新 tags/updated
            top["tags"] = sorted(set((top.get("tags") or []) + (tags or [])))
            top["updated"] = _now()
            top["updates"] = top.get("updates", 0) + 1
            if top["text"] != text and len(top.get("history", [])) < 20:
                top.setdefault("history", []).append({"text": top["text"], "ts": top["ts"]})
            top["ts"] = _now()
            self._consolidate()
            return {"action": "UPDATE", "reason": f"同主题记忆存在(相似度{scored[0][0]:.2f})，更新而非重复新增",
                    "text": text, "fact": top, "similar": similar, "updated": True}
        # 3) ADD
        added = self.add_fact(text, tags)
        self._consolidate()
        return {"action": "ADD" if added else "SKIP",
                "reason": "新增事实" if added else "完全重复，跳过",
                "text": text, "updated": added}

    # ---- 记忆自动沉淀（用后自动存，非手动点）----
    def _auto_state_path(self) -> str:
        return os.path.join(self.dir, "auto.json")

    def _load_auto_state(self) -> dict:
        return self._load(self._auto_state_path(),
                          {"count": 0, "updated": "", "events": []})

    def _save_auto_state(self, st: dict) -> None:
        self._save(self._auto_state_path(), st)

    def auto_state(self) -> dict:
        """自动沉淀统计（供前端展示「自动积累状态」）。"""
        return self._load_auto_state()

    @staticmethod
    def _is_noise(text: str) -> bool:
        """过滤无沉淀价值的噪音（占位/问候/过短），避免污染自动记忆。"""
        t = (text or "").strip()
        if len(t) < 6:
            return True
        low = t.lower()
        if low in {"hello", "hi", "test", "测试", "你好", "您好", "你好吗",
                   "我该如何使用", "web端验证记忆", "验证记忆"}:
            return True
        # 纯占位/临时标记且很短 → 视为噪音
        if len(t) < 12 and any(k in low for k in ("测试", "临时", "验证", "placeholder")):
            return True
        return False

    def auto_sediment(self, text: str, tags: list = None, source: str = "auto") -> dict:
        """自动沉淀入口：agent 主流程（问答/审查/决策/任务完成后）用后自动写入。

        与手动 add_fact 区别：
          - 自动过滤噪音（_is_noise）
          - 复用 write() 决策层（去重/同主题更新/新增），不产生重复堆积
          - 打上 auto+source 标签、累计统计，供前端展示「自动积累」
        失败静默返回，绝不打断主流程（agent 调用处 try 包裹）。返回 {action, auto, source,...}。
        """
        try:
            if not text or not isinstance(text, str):
                return {"action": "SKIP", "reason": "空文本", "auto": True, "source": source}
            t = text.strip()
            if self._is_noise(t):
                return {"action": "SKIP", "reason": "噪音/过短", "auto": True, "source": source}
            tags = list(dict.fromkeys((tags or []) + ["auto", source]))
            r = self.write(t, tags=tags)
            if r.get("updated"):
                st = self._load_auto_state()
                st["count"] = st.get("count", 0) + 1
                st["updated"] = _now()
                st.setdefault("events", []).append(
                    {"text": t[:60], "action": r.get("action"),
                     "source": source, "ts": _now()})
                st["events"] = st["events"][-50:]
                self._save_auto_state(st)
            r.update({"auto": True, "source": source})
            return r
        except Exception as e:  # noqa: BLE001 静默兜底
            return {"action": "SKIP", "reason": f"error:{e}",
                    "auto": True, "source": source}

    def update_fact(self, target_text: str, new_text: str, tags: list = None) -> dict:
        """显式 UPDATE 一条记忆（对齐 Mem0 update 语义）。"""
        facts = self._load_facts()
        for f in facts:
            if f["text"] == target_text:
                if f.get("history", []).__len__() < 20:
                    f.setdefault("history", []).append({"text": f["text"], "ts": f["ts"]})
                f["text"] = new_text
                f["h"] = self._hash(new_text)
                if tags:
                    f["tags"] = sorted(set((f.get("tags") or []) + tags))
                f["updated"] = _now()
                self._consolidate()
                return {"ok": True, "action": "UPDATE", "fact": f}
        return {"ok": False, "action": "UPDATE", "reason": "目标记忆不存在"}

    def delete_fact(self, text: str = None, h: str = None) -> dict:
        """DELETE 一条记忆（按文本或哈希）。返回是否删除。"""
        facts = self._load_facts()
        before = len(facts)
        if text is not None:
            facts = [f for f in facts if f["text"] != text]
        elif h is not None:
            facts = [f for f in facts if f.get("h") != h]
        self._consolidate(facts)
        return {"ok": len(facts) != before, "action": "DELETE",
                "deleted": before - len(facts)}

    def search(self, query: str, top_k: int = 5, semantic: bool = True):
        """事实层检索。优先 embed 向量（P1-5），无 embed 回退词重叠。

        P1 性能优化：embed 向量按事实哈希缓存(_emb_cache)，仅首次计算，
        重复 search 不再逐条重复调用 embed（批量/缓存），大幅降低检索开销。
        """
        facts = self._load_facts()
        if semantic:
            q_emb = self._try_embed(query)
            if q_emb is not None:
                vecs = self._emb_cache
                # 只对尚未缓存的条目标量化一次（缓存命中直接复用）
                for f in facts:
                    h = f.get("h", id(f))
                    if h not in vecs:
                        v = self._try_embed(f["text"])
                        if v:
                            vecs[h] = v
                scored = sorted(
                    facts,
                    key=lambda f: _cosine(q_emb, vecs.get(f.get("h", id(f)), [])),
                    reverse=True)
            else:
                scored = sorted(facts, key=lambda f: _overlap(f["text"], query), reverse=True)
        else:
            scored = facts
        self._maybe_consolidate()
        return scored[:top_k]

    def _try_embed(self, text: str):
        """尝试用配置的 embed 模型向量化。失败返回 None（回退词重叠）。

        健壮性：一旦探测到 embed 不可用(无 ollama / 连接失败)即标记 unavailable，
        后续不再重复等待，避免 search 在 embed 端点宕机时反复阻塞。
        """
        if getattr(self, "_embed_unavailable", False):
            return None
        try:
            import socket
            old_to = socket.getdefaulttimeout()
            socket.setdefaulttimeout(3)  # 连接探测上限，防无限阻塞
            try:
                from solo import provider as provider_mod
                p = provider_mod.Provider.from_file()
                return p.embed(text)
            finally:
                socket.setdefaulttimeout(old_to)
        except Exception:
            self._embed_unavailable = True
            return None

    # ---- 温域·场景层 ----
    @staticmethod
    def _safe_name(name: str) -> str:
        """防路径穿越：场景/会话名仅允许 字母数字_-.，杜绝 ../ 绝对路径 控制符。"""
        n = str(name)
        if not n or n in (".", ".."):
            raise ValueError(f"非法名称: {name!r}")
        if os.path.sep in n or (os.path.altsep and os.path.altsep in n) \
                or "/" in n or "\\" in n or "\x00" in n or n.startswith("."):
            raise ValueError(f"非法名称(含路径分隔/穿越): {name!r}")
        if not re.fullmatch(r"[A-Za-z0-9_\-.]+", n):
            raise ValueError(f"非法名称(仅允许字母数字_-.): {name!r}")
        return n

    def set_scenario(self, name: str, content: str) -> None:
        """场景层：项目完整上下文（整包恢复）。"""
        safe = self._safe_name(name)
        self._save(os.path.join(self.dir, "scenarios", f"{safe}.json"),
                   {"name": safe, "content": content, "ts": _now()})

    def get_scenario(self, name: str) -> str:
        safe = self._safe_name(name)
        d = self._load(os.path.join(self.dir, "scenarios", f"{safe}.json"), None)
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
        safe = self._safe_name(name)
        self._save(os.path.join(self.dir, "sessions", f"{safe}.json"),
                   {"name": safe, "content": content, "ts": _now()})

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
        self._consolidate()
        return added

    def export_markdown(self, out_dir: str) -> None:
        """导出事实层为 Markdown（可回写 Obsidian）。"""
        os.makedirs(out_dir, exist_ok=True)
        facts = self._load_facts()
        with open(os.path.join(out_dir, "solo-memory.md"), "w", encoding="utf-8") as fh:
            for f in facts:
                fh.write("- " + f["text"] + "\n")

    # ---- OptMem 互通(可选增强): 把经验/方法论沉淀进 OptMem 全局记忆 ----
    def optmem_note(self, text: str):
        """调外置记忆目录 memo note 沉淀一条全局记忆(经验/方法论)。

        用于 FDE 工具箱经验/方法论跨项目、跨会话复用。失败静默返回, 不打断主流程。
        """
        return optmem_note(text)

    def optmem_search(self, query: str, top_k: int = 5):
        """调外置记忆目录 memo_search.py 语义检索 OptMem 记忆。返回匹配文本列表。"""
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
# 把 FDE 工具箱经验/方法论沉淀进 OptMem 全局记忆（可选增强，由环境变量指定），跨项目、跨会话复用。
# 失败静默返回，绝不打断主流程；可用环境变量 OPTMEM_NOTE=0 关闭。
_MEMO = os.environ.get("OPTMEM_MEMO", os.path.join(os.path.expanduser("~"), "optmem", "memo"))
_MEMO_SEARCH = os.environ.get("OPTMEM_MEMO_SEARCH", os.path.join(os.path.expanduser("~"), "optmem", "memo_search.py"))
_MEMORY_DIR = os.environ.get("OPTMEM_MEMORY_DIR", os.path.join(os.path.expanduser("~"), "optmem", "memory"))
_OPTMEM_ENABLED = os.environ.get("OPTMEM_NOTE", "1").lower() not in ("0", "false", "no", "off")


def optmem_note(text: str):
    """调外置记忆目录 memo note 沉淀一条全局记忆。返回 (ok, 消息)。"""
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
    """调外置记忆目录 memo_search.py 语义检索 OptMem 记忆。失败返回 []。"""
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
