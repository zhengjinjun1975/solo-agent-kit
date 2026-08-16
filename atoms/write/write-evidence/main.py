# -*- coding: utf-8 -*-
"""write-evidence 原子：证据账本+事实核查。复用 solo/factory/evidence.py 核心(零改动)。"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _e():
    from solo.factory import evidence as _m  # noqa: PLC0415
    return _m

class WriteEvidenceAtom(AtomicAgent):
    def capabilities(self):
        return ["write.evidence"]
    def _run(self, op: str = "ledger", **params):
        mod = _e()
        text = params.get("text")
        if op == "ledger":
            if text is None:
                return fail("ledger 需 text")
            return ok({"ledger": mod.build_ledger(text, source_rows=params.get("source_rows"))})
        if op == "check":
            if text is None:
                return fail("check 需 text")
            return ok({"result": mod.fact_check(text, source_rows=params.get("source_rows"))})
        return fail(f"未知 op: {op}")

def _main():
    a = WriteEvidenceAtom(name="write-evidence", agent="write", version="0.1.0")
    a.load()
    src = [{"设备": "水泵A", "振动": 5.2, "温度": 45}]
    r = a.run(op="ledger", text="水泵A 振动 5.2mm/s，温度 45℃", source_rows=src)
    assert r.get("ok"), "evidence ledger 失败"
    r2 = a.run(op="check", text="水泵A 振动 5.2mm/s，温度 99℃", source_rows=src)
    assert r2.get("ok"), "evidence check 失败"
    print("write-evidence 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
