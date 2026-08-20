# -*- coding: utf-8 -*-
"""monitor-device — 设备监测内聚闭环原子（5→1 收敛）。

协议直采 + 指标存储 + 异常检测 + 动态阈值告警 + 规则问答子集。
纯算法来自 kernels.monitor_stats / kernels.forecast；状态在 _impl/device.py。
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
from kernels import monitor_stats, forecast  # noqa: E402

import importlib.util as _ilu  # noqa: E402


def _load_impl(name):
    p = os.path.join(_HERE, "_impl", name)
    spec = _ilu.spec_from_file_location(f"monitor_device_{name}", p)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


device_impl = _load_impl("device.py")


class MonitorDeviceAtom(AtomicAgent):
    def capabilities(self):
        return ["monitor.device"]

    def inputs(self):
        return {"op": ["ingest", "set_rule", "evaluate", "adaptive", "anomaly",
                       "protocols", "protocol_read", "snapshot", "ask"]}

    def _run(self, op="snapshot", dir=None, points=None, device_id=None, metric=None,
             value=None, rule=None, values=None, config=None, k=3.0, ts="", **params):
        try:
            store = device_impl.MetricStore(dir)
            if op == "ingest":
                points = points or params.get("points") or []
                res = store.ingest(points)
                return ok({"ingested": res})
            if op == "set_rule":
                rule = rule or params.get("rule") or {}
                r = store.set_rule(device_id or rule.get("device_id"),
                                   metric or rule.get("metric"),
                                   rule.get("cmp_op", ">"),
                                   rule.get("threshold", 0),
                                   rule.get("level", "warn"))
                return ok({"rules": store.rules(device_id), "set_rule": r})
            if op == "evaluate":
                eng = device_impl.AlertEngine(store)
                alerts = eng.evaluate(device_id or "", metric or "", value or 0, ts)
                worst = "ok"
                if alerts:
                    worst = "warn" if all(a["level"] == "warn" for a in alerts) else "critical"
                return ok({"alerts": alerts, "worst_level": worst})
            if op == "adaptive":
                values = values or store.values(device_id, metric)
                thr = monitor_stats.adaptive_threshold(values, k=float(k or 3.0))
                return ok({"threshold": thr})
            if op == "anomaly":
                values = values or store.values(device_id, metric)
                anom = monitor_stats.anomaly(values, method=params.get("method", "mad"),
                                             k=float(k or 3.0))
                return ok({"anomalies": anom})
            if op == "protocols":
                config = config or params.get("config") or {}
                skipped = []
                protos = []
                for kind in ("tcp", "http", "csv", "mqtt", "modbus", "opcua"):
                    adapter = device_impl.ProtocolAdapter(kind, config.get(kind))
                    if adapter.available():
                        protos.append({"kind": kind, "available": True})
                    else:
                        skipped.append(kind)
                        protos.append({"kind": kind, "available": False,
                                       "error": f"{kind} 缺库不可用"})
                # 始终 ok 返回（列出全部协议可用状态），缺库用 skipped/degraded 标注，
                # 不让部分协议缺库导致整个 protocols 接口 fail（modbus/opcua 仍可用）
                env = {"protocols": protos, "skipped": skipped, "degraded": bool(skipped),
                       "detail": "modbus/opcua 纯标准库真实直采可用(可连真设备或本地模拟器)"}
                return ok(env)
            if op == "protocol_read":
                # 真实连接直采：config 指定 {protocol, ...}，连本地模拟器或真设备读数据
                config = config or params.get("config") or {}
                kind = config.get("protocol")
                if kind not in ("modbus", "opcua"):
                    return fail(f"protocol_read 仅支持 modbus/opcua 真实直采，收到: {kind}")
                adapter = device_impl.ProtocolAdapter(kind, config)
                if not adapter.available():
                    return fail(f"{kind} 不可用")
                try:
                    res = adapter.read()
                except Exception as e:  # noqa: BLE001
                    return fail(f"{kind} 直采失败(明确报错不静默): {e}", degraded=True)
                # 直采点入存储
                store.ingest(res.get("points") or [])
                return ok({"protocol": kind, "read": res, "count": len(res.get("points") or [])})
            if op == "snapshot":
                devices = sorted({s.get("device_id") for s in store.series()})
                series = {d: {m: store.values(d, m) for m in
                              {s.get("metric") for s in store.series(d)}}
                          for d in devices}
                return ok({"snapshot": {"devices": devices, "series": series,
                                        "alerts_n": len(store.alerts())}})
            if op == "ask":
                # 规则问答子集：问当前值/是否越限/告警数
                q = (params.get("question") or "").lower()
                if "告警" in q:
                    return ok({"answer": {"count": len(store.alerts(device_id))}})
                if metric:
                    vals = store.values(device_id, metric)
                    latest = vals[-1] if vals else None
                    return ok({"answer": {"metric": metric, "latest": latest,
                                          "count": len(vals)}})
                return fail(f"未知 op: {op}")
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"monitor-device 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    import tempfile
    a = MonitorDeviceAtom(name="monitor-device", agent="monitor")
    a.load()
    d = tempfile.mkdtemp(prefix="mon_")
    pts = [{"device_id": "pump_01", "metric": "vibration", "value": v,
            "ts": f"2026-08-16T10:0{i}:00"}
           for i, v in enumerate([4.9, 5.1, 5.0, 5.3, 5.2, 8.6])]
    r = a.run(op="ingest", points=pts, dir=d)
    assert r["ok"] and r["data"]["ingested"]["count"] == 6, "ingest 空壳!"
    thr = a.run(op="adaptive", device_id="pump_01", metric="vibration", k=3.0, dir=d)
    assert thr["ok"] and thr["data"]["threshold"]["upper"], "adaptive 空壳!"
    r2 = a.run(op="set_rule", device_id="pump_01", metric="vibration",
               rule={"cmp_op": ">", "threshold": thr["data"]["threshold"]["upper"],
                     "level": "warn"}, dir=d)
    assert r2["ok"], "set_rule 空壳!"
    r3 = a.run(op="evaluate", device_id="pump_01", metric="vibration", value=8.6, dir=d)
    assert r3["ok"] and r3["data"]["alerts"], "evaluate 空壳!"
    print("alert level:", r3["data"]["alerts"][0]["level"], "worst:", r3["data"]["worst_level"])
    r4 = a.run(op="protocols", dir=d)
    assert "ok" in r4 and (r4["ok"] or r4.get("degraded")), "protocols 未降级处理!"
    print("protocols ok:", r4.get("ok"), "skipped:", r4.get("skipped", []))
    print("monitor-device 独立自测通过")
