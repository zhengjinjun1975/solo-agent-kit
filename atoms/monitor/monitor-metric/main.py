# -*- coding: utf-8 -*-
"""monitor-metric 原子：指标存储(MetricStore)。复用 solo/factory/monitor.py 核心(零改动)。"""
from __future__ import annotations
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _store():
    from solo.factory import monitor as _m  # noqa: PLC0415
    return _m

class MonitorMetricAtom(AtomicAgent):
    def capabilities(self):
        return ["monitor.metric"]
    def _run(self, op: str = "latest", dir: str = None, **params):
        mod = _store()
        workdir = dir or os.path.join(_ROOT, "data", "monitor")
        st = mod.MetricStore(workdir)
        if op == "ingest":
            points = params.get("points") or []
            # MetricStore.ingest(list) 只回最后一条，逐条 ingest 以回全量列表
            recs = [st.ingest(p) for p in points] if isinstance(points, list) else st.ingest(points)
            return ok({"ingested": recs})
        if op == "latest":
            device = params.get("device_id"); metric = params.get("metric")
            # MetricStore.latest 返回单条记录(dict)或 None
            row = st.latest(device_id=device, metric=metric)
            return ok({"latest": row})
        if op == "alerts":
            return ok({"alerts": st.alerts(params.get("state"), limit=params.get("limit", 20))})
        if op == "range":
            device, metric = params.get("device_id"), params.get("metric")
            minutes = params.get("minutes", 5)
            return ok({"points": st.window(device, metric, minutes=minutes)})
        return fail(f"未知 op: {op}")

def _main():
    a = MonitorMetricAtom(name="monitor-metric", agent="monitor", version="0.1.0")
    a.load()
    import tempfile
    d = tempfile.mkdtemp(prefix="fde_metric_")
    r = a.run(op="ingest", dir=d, points=[{"device_id":"pump_01","metric":"vibration","value":2.31,"ts":"2026-08-16T10:00:00"}])
    assert r.get("ok"), "monitor-metric ingest 失败"
    r2 = a.run(op="latest", dir=d)
    assert r2.get("ok") and r2["data"]["latest"] and \
        r2["data"]["latest"].get("device_id") == "pump_01", \
        f"monitor-metric latest 断言形态错误: {r2}"
    print("monitor-metric 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
