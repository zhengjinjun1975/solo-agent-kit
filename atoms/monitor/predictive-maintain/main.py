# -*- coding: utf-8 -*-
"""predictive-maintain — 预测性维护原子（故障预警/趋势预测/维修建议）。

纯算法来自 kernels.forecast / kernels.spc；maintain 维修建议可选经 $ref 注入 diagnose.kb。
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
from kernels import forecast, spc  # noqa: E402


class PredictiveMaintainAtom(AtomicAgent):
    def capabilities(self):
        return ["predict.maintain"]

    def inputs(self):
        return {"op": ["forecast", "risk", "maintain"]}

    def _run(self, op="risk", dir=None, series=None, values=None, device_id=None,
             metric=None, window=3, k=3.0, failure_mode=None, **params):
        try:
            vals = series if series is not None else values
            vals = vals or []
            if op == "forecast":
                f = forecast.forecast_series(vals, horizon=int(params.get("horizon", 1)))
                return ok({"forecast": f})
            if op == "risk":
                f = forecast.forecast_series(vals)
                level = forecast.risk_level([v for v in vals if isinstance(v, (int, float))])
                next_maintain = forecast.rul(vals, params.get("threshold") or (f.get("upper") if isinstance(f, dict) else None)) \
                    if isinstance(f, dict) else forecast.rul(vals, None)
                return ok({"risk": {"level": level, "predictions": f,
                                    "next_maintain": next_maintain}})
            if op == "maintain":
                # 维修建议：优先吃注入的 kb 命中（经 run_flow $ref），否则内核故障映射
                kb_hit = params.get("kb_hit") or params.get("hit")
                if kb_hit:
                    advice = {"actions": kb_hit.get("actions") or ["按知识库建议处理"],
                              "parts": kb_hit.get("parts") or [], "from_kb": True,
                              "estimated_cost": kb_hit.get("estimated_cost", 0)}
                else:
                    advice = forecast.fault_advice(failure_mode or params.get("failure", ""))
                return ok({"advice": advice})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"predictive-maintain 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    a = PredictiveMaintainAtom(name="predictive-maintain", agent="monitor")
    a.load()
    seq = [4.0, 4.2, 4.5, 4.9, 5.2, 5.6, 6.1, 6.5, 7.0, 7.6]
    r = a.run(op="forecast", series=seq)
    assert r["ok"] and r["data"]["forecast"]["next"], "forecast 空壳!"
    print("next:", r["data"]["forecast"]["next"])
    r2 = a.run(op="risk", series=seq, k=3.0)
    assert r2["ok"] and r2["data"]["risk"]["level"], "risk 空壳!"
    print("risk level:", r2["data"]["risk"]["level"])
    r3 = a.run(op="maintain", failure_mode="轴承磨损", device_id="pump_01")
    assert r3["ok"] and r3["data"]["advice"]["actions"], "maintain 空壳!"
    print("advice actions:", r3["data"]["advice"]["actions"])
    print("predictive-maintain 独立自测通过")
