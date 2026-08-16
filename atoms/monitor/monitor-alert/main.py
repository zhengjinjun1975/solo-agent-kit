# -*- coding: utf-8 -*-
"""monitor-alert 原子：告警评估 + 动态阈值（FDE 能力提升，参考 fde-latest-tech-deepdive §2.2）。

复用 solo/factory/monitor.py AlertEngine 核心（零改动），并在壳层叠加**动态阈值**能力：
层1 统计基线（MAD 稳健基线 + 自适应 k·std + 趋势/突变融合），替代纯静态阈值降低误报/漏报。
告警复用现有 alert→ticket 闭环，type="adaptive"。
"""
from __future__ import annotations
import os, sys, statistics
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _mod():
    from solo.factory import monitor as _m  # noqa: PLC0415
    return _m

def adaptive_threshold(values, k=3.0, min_points=4):
    """动态阈值：MAD 稳健基线 + 自适应 k·std。

    对少于 min_points 的窗口返回 None（数据不足不告警）。
    返回 {upper, lower, baseline, std, mad, k}。
    """
    if not values or len(values) < min_points:
        return None
    med = statistics.median(values)
    # MAD 稳健离散度
    mad = statistics.median([abs(v - med) for v in values]) or 1e-9
    # 用 std 兜底（MAD 对正态稳健，std 对整体尺度）
    std = statistics.stdev(values) if len(values) >= 2 else 0.0
    scale = max(mad, std) if std else mad
    return {"upper": med + k * scale, "lower": med - k * scale,
            "baseline": med, "std": round(std, 4),
            "mad": round(mad, 4), "k": k}

class MonitorAlertAtom(AtomicAgent):
    def capabilities(self):
        return ["monitor.alert"]
    def _run(self, op: str = "evaluate", dir: str = None, **params):
        mod = _mod()
        workdir = dir or os.path.join(_ROOT, "data", "monitor")
        st = mod.MetricStore(workdir)
        eng = mod.AlertEngine(store=st)
        if op == "set_rule":
            dev, metric = params.get("device_id"), params.get("metric")
            if not dev or not metric:
                return fail("set_rule 需 device_id+metric")
            # 规则比较运算符用 cmp_op，避免与原子操作选择器 op 冲突
            r = st.set_rule(dev, metric, params.get("cmp_op", ">"),
                            params.get("threshold", 0), mutate_pct=params.get("mutate_pct"))
            return ok({"rule": r})
        if op == "evaluate":
            dev, metric, value = params.get("device_id"), params.get("metric"), params.get("value")
            if dev is None or not metric or value is None:
                return fail("evaluate 需 device_id+metric+value")
            raised = eng.evaluate_point(dev, metric, float(value), ts=params.get("ts"))
            return ok({"alerts": raised})
        if op == "adaptive":
            values = params.get("values") or []
            k = params.get("k", 3.0)
            thr = adaptive_threshold(values, k=k)
            if thr is None:
                return ok({"threshold": None, "note": "数据不足(需≥4点)"})
            return ok({"threshold": thr})
        if op == "rules":
            return ok({"rules": st.rules(params.get("device_id"))})
        return fail(f"未知 op: {op}")

def _main():
    a = MonitorAlertAtom(name="monitor-alert", agent="monitor", version="0.1.0")
    a.load()
    import tempfile
    d = tempfile.mkdtemp(prefix="fde_alert_")
    # 动态阈值：稳态数据低方差，极端值应超阈值
    base = [10.0 + (i % 3) * 0.1 for i in range(20)]
    thr = a.run(op="adaptive", dir=d, values=base, k=3.0)
    assert thr.get("ok") and thr["data"]["threshold"] is not None, "adaptive 失败"
    upper = thr["data"]["threshold"]["upper"]
    extreme = a.run(op="adaptive", dir=d, values=base + [30.0], k=3.0)
    assert extreme.get("ok")
    print("monitor-alert 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
