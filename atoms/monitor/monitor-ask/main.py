# -*- coding: utf-8 -*-
"""monitor-ask 原子：AI 问数(MonitorAsk)。复用 solo/factory/monitor.py 核心(零改动)。"""
from __future__ import annotations
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _mod():
    from solo.factory import monitor as _m  # noqa: PLC0415
    return _m

class MonitorAskAtom(AtomicAgent):
    def capabilities(self):
        return ["monitor.ask"]
    def _run(self, op: str = "ask", dir: str = None, **params):
        mod = _mod()
        workdir = dir or os.path.join(_ROOT, "data", "monitor")
        st = mod.MetricStore(workdir)
        eng = mod.AlertEngine(st)
        ask = mod.MonitorAsk(store=st, engine=eng)
        if op == "ask":
            q = params.get("question")
            if not q:
                return fail("ask 需 question")
            return ok({"answer": ask.ask(q)})
        if op == "seed":
            for pt in (params.get("points") or []):
                st.ingest([pt])
            return ok({"seeded": len(params.get("points") or [])})
        return fail(f"未知 op: {op}")

def _main():
    a = MonitorAskAtom(name="monitor-ask", agent="monitor", version="0.1.0")
    a.load()
    import tempfile
    d = tempfile.mkdtemp(prefix="fde_ask_")
    a.run(op="seed", dir=d, points=[{"device_id":"pump_01","metric":"vibration","value":5.0,"ts":"2026-08-16T10:00:00"}])
    r = a.run(op="ask", dir=d, question="最近有哪些告警")
    assert r.get("ok"), "monitor-ask 失败"
    print("monitor-ask 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
