# -*- coding: utf-8 -*-
"""memory-fact 原子：三层两域记忆。复用 solo/memory.py Memory 核心(零改动)。"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _mem():
    from solo import memory as _m  # noqa: PLC0415
    return _m

class MemoryFactAtom(AtomicAgent):
    def capabilities(self):
        return ["memory.fact"]
    def _run(self, op: str = "add", dir: str = None, **params):
        mod = _mem()
        workdir = dir or os.path.join(_ROOT, "data", "memory")
        m = mod.Memory(workdir)
        if op == "add":
            text = params.get("text")
            if not text:
                return fail("add 需 text")
            return ok({"added": m.add_fact(text, tags=params.get("tags"))})
        if op == "write":
            text = params.get("text")
            if not text:
                return fail("write 需 text")
            return ok({"decision": m.write(text, tags=params.get("tags"),
                                            threshold=params.get("threshold", 0.6))})
        if op == "search":
            q = params.get("query")
            if not q:
                return fail("search 需 query")
            hits = m.search(q, top_k=params.get("top_k", 5))
            return ok({"hits": hits})
        if op == "facts":
            return ok({"facts": m._load_facts()})
        if op == "profile":
            return ok({"profile": m.profile_text()})
        return fail(f"未知 op: {op}")

def _main():
    a = MemoryFactAtom(name="memory-fact", agent="memory", version="0.1.0")
    a.load()
    import tempfile
    d = tempfile.mkdtemp(prefix="fde_mem_")
    r = a.run(op="add", dir=d, text="水泵振动 5.0mm/s 异常")
    assert r.get("ok") and r["data"]["added"] is True, "memory add 失败"
    r2 = a.run(op="add", dir=d, text="水泵振动 5.0mm/s 异常")
    assert r2["data"]["added"] is False, "去重失败"
    r3 = a.run(op="search", dir=d, query="振动")
    assert r3.get("ok")
    print("memory-fact 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
