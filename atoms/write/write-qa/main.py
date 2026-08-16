# -*- coding: utf-8 -*-
"""write-qa 原子：六维中文写作检查。复用 solo/writing.py 核心(零改动)。"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _w():
    from solo import writing as _m  # noqa: PLC0415
    return _m

class WriteQaAtom(AtomicAgent):
    def capabilities(self):
        return ["write.qa"]
    def _run(self, op: str = "scan", **params):
        mod = _w()
        text = params.get("text")
        if op == "scan":
            if text is None:
                return fail("scan 需 text")
            return ok({"report": mod.scan(text, filepath=params.get("filepath"))})
        if op == "ai_taste":
            if text is None:
                return fail("ai_taste 需 text")
            return ok({"report": mod.ai_taste(text, style=params.get("style", "report"))})
        if op == "generate_doc":
            topic = params.get("topic")
            if not topic:
                return fail("generate_doc 需 topic")
            return ok({"doc": mod.generate_doc(topic, kind=params.get("kind", "readme"))})
        return fail(f"未知 op: {op}")

def _main():
    a = WriteQaAtom(name="write-qa", agent="write", version="0.1.0")
    a.load()
    r = a.run(op="scan", text="本报告旨在确认交付范围，确保验收通过。")
    assert r.get("ok"), "write scan 失败"
    r2 = a.run(op="ai_taste", text="这是测试文本用于检查。")
    assert r2.get("ok"), "write ai_taste 失败"
    print("write-qa 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
