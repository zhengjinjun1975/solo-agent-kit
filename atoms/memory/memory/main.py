# -*- coding: utf-8 -*-
"""memory — 三层两域记忆 + OptMem 原子（合并 memory-fact + memory-optmem）。

真下沉：纯检索打分来自 kernels.memory_score，状态存储在此原子 _impl/。
不 import solo.factory，单原子可独立运行。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402
from kernels import memory_score  # noqa: E402

import importlib.util as _ilu  # noqa: E402


def _load_impl(name):
    p = os.path.join(_HERE, "_impl", name)
    spec = _ilu.spec_from_file_location(f"memory_{name}", p)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_impl = _load_impl("memory_store.py")
MemoryStore = _impl.MemoryStore


class MemoryAtom(AtomicAgent):
    def capabilities(self):
        return ["memory.core"]

    def inputs(self):
        return {"op": ["add", "search", "profile", "sediment", "optmem"]}

    def _run(self, op="search", dir=None, text=None, query=None, tags=None,
             source="manual", top_k=5, facts=None, **params):
        try:
            st = MemoryStore(dir)
            if op == "add":
                added = st.add_fact(text, tags)
                return ok({"stored": {"added": added, "text": text},
                           "facts_n": len(st.facts())})
            if op == "search":
                query = query or text or ""
                fs = st.facts()
                scored = sorted(
                    ({"fact": f, "score": memory_score.semantic_score(query, f.get("text", ""))}
                     for f in fs),
                    key=lambda x: x["score"], reverse=True)[:int(top_k or 5)]
                return ok({"hits": scored, "facts_n": len(fs)})
            if op == "profile":
                if text is not None:
                    st.set_profile(str(query or "key"), text)
                return ok({"profile": st.profile()})
            if op == "sediment":
                if memory_score.is_noise(text or ""):
                    return ok({"stored": {"skipped": True, "reason": "噪音"},
                               "facts_n": len(st.facts())})
                added = st.add_fact(text, tags)
                return ok({"stored": {"added": added, "source": source},
                           "facts_n": len(st.facts())})
            if op == "optmem":
                if text is not None:
                    n = st.optmem_note(text)
                    return ok({"stored": {"note_count": n}})
                notes = st.optmem_notes()
                query = query or ""
                scored = sorted(
                    ({"text": x.get("text", ""),
                      "score": memory_score.semantic_score(query, x.get("text", ""))}
                     for x in notes),
                    key=lambda z: z["score"], reverse=True)[:int(top_k or 5)]
                return ok({"hits": scored, "facts_n": len(notes)})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"memory 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    import tempfile
    a = MemoryAtom(name="memory", agent="memory")
    a.load()
    d = tempfile.mkdtemp(prefix="mem_")
    r = a.run(op="add", text="泵站 pump_01 振动值偏高，疑似轴承磨损", tags=["monitor"], dir=d)
    assert r["ok"] and r["data"]["stored"]["added"] is True, "add 空壳!"
    r2 = a.run(op="search", query="轴承磨损 振动", top_k=3, dir=d)
    assert r2["ok"] and r2["data"]["hits"], "search 空壳!"
    print("hit score:", r2["data"]["hits"][0]["score"])
    r3 = a.run(op="sediment", text="测试", dir=d)
    assert r3["data"]["stored"]["skipped"] is True, "噪音过滤失效!"
    r4 = a.run(op="optmem", text="经验：振动越限先查轴承", dir=d)
    assert r4["ok"] and r4["data"]["stored"]["note_count"] == 1
    print("memory 独立自测通过")
