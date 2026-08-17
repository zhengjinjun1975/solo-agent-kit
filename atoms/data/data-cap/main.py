# -*- coding: utf-8 -*-
"""data-cap — 数据接入/清洗/SPC/CPK/描述统计/趋势/报告 原子。

真下沉：纯算法来自 kernels.spc（无 IO），op 分发 + IO + 状态在此原子实现。
不 import solo.factory，单原子可独立运行。
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402
from kernels import spc as spc_kernel  # noqa: E402


class DataCapAtom(AtomicAgent):
    def capabilities(self):
        return ["data.cap"]

    def inputs(self):
        return {"op": ["clean", "spc", "cpk", "describe", "trend", "report"]}

    def _run(self, op="describe", dir=None, rows=None, values=None,
             col=None, usl=None, lsl=None, **params):
        try:
            if op == "clean":
                rows = rows or params.get("rows") or []
                cleaned, metrics = spc_kernel.clean(rows)
                self._save(dir, "clean_metrics.json", metrics)
                return ok({"cleaned_rows": cleaned, "metrics": metrics})
            if op == "spc":
                values = values or params.get("values") or []
                chart = spc_kernel.control_chart(values)
                self._save(dir, "spc_chart.json", chart)
                return ok({"spc": chart})
            if op == "cpk":
                values = values or params.get("values") or []
                result = spc_kernel.cpk(values, usl=usl, lsl=lsl)
                self._save(dir, "spc_cpk.json", result)
                return ok({"cpk": result})
            if op == "describe":
                values = values or params.get("values") or []
                return ok({"describe": spc_kernel.describe(values)})
            if op == "trend":
                values = values or params.get("values") or []
                return ok({"trend": spc_kernel.trend(values),
                           "anomalies": spc_kernel.detect_anomaly(values)})
            if op == "report":
                rows = rows or params.get("rows") or []
                rep = spc_kernel.report(rows)
                self._save(dir, "data_report.json", rep)
                return ok({"report": rep})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"data-cap 运行异常: {e}", degraded=True)

    @staticmethod
    def _save(dir, name, data):
        if not dir:
            return
        os.makedirs(dir, exist_ok=True)
        with open(os.path.join(dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    a = DataCapAtom(name="data-cap", agent="data")
    a.load()
    seq = [5.0, 5.2, 4.8, 5.1, 5.3, 5.0, 8.6, 5.2, 5.1, 5.4]
    r = a.run(op="spc", values=seq)
    assert r["ok"] and r["data"]["spc"]["judge"], "SPC 空壳!"
    print("spc:", r["data"]["spc"]["judge"], "mean", r["data"]["spc"]["mean"])
    c = a.run(op="cpk", values=seq, usl=7.0, lsl=3.0)
    assert c["ok"] and c["data"]["cpk"]["cpk"] is not None, "CPK 空壳!"
    print("cpk:", c["data"]["cpk"]["cpk"], c["data"]["cpk"]["judge"])
    d = a.run(op="describe", values=seq)
    assert d["ok"] and d["data"]["describe"]["count"] == len(seq)
    print("describe count:", d["data"]["describe"]["count"])
    print("data-cap 独立自测通过")
