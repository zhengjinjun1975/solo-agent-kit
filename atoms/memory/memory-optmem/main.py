# -*- coding: utf-8 -*-
"""memory-optmem 原子：OptMem 全局记忆互通(可选增强)。复用 solo/memory.py 核心(零改动)。

失败静默降级（不打断主流程）：OptMem 不可用时返回 degraded 信封。
"""
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

class MemoryOptmemAtom(AtomicAgent):
    def capabilities(self):
        return ["memory.optmem"]
    def _run(self, op: str = "note", **params):
        mod = _mem()
        if op == "note":
            text = params.get("text")
            if not text:
                return fail("note 需 text")
            okk, msg = mod.optmem_note(text)
            return ok({"ok": okk, "msg": msg, "degraded": not okk})
        if op == "search":
            q = params.get("query")
            if not q:
                return fail("search 需 query")
            hits = mod.optmem_search(q, top_k=params.get("top_k", 5))
            return ok({"hits": hits})
        return fail(f"未知 op: {op}")

def _main():
    a = MemoryOptmemAtom(name="memory-optmem", agent="memory", version="0.1.0")
    a.load()
    r = a.run(op="note", text="solo FDE 原子化重构完成")
    # OptMem 不可用也应降级返回(不抛), 可自测
    assert r.get("ok"), "optmem note 失败"
    print("memory-optmem 独立自测通过(含降级), 0 失败")

if __name__ == "__main__":
    _main()
