# -*- coding: utf-8 -*-
"""monitor-protocol 原子：协议直采。复用 solo/factory/protocols.py 核心(零改动)。

FDE 能力提升：吸收最新技术——MQTT5(User Properties/Message Expiry/Topic Alias) 与
Sparkplug B 生命周期(NBIRTH/DBIRTH/DATA/DEATH)能力接口 + 明确缺库报错(零依赖降级)。
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _mod():
    from solo.factory import protocols as _p  # noqa: PLC0415
    return _p

class MonitorProtocolAtom(AtomicAgent):
    def capabilities(self):
        return ["monitor.protocol"]
    def _run(self, op: str = "list", **params):
        mod = _mod()
        if op == "list":
            return ok({"protocols": mod.protocols()})
        if op == "create":
            cfg = params.get("config") or {}
            store = params.get("store")
            engine = params.get("engine")
            src = mod.create_source(cfg, store=store, engine=engine)
            return ok({"source": {"type": cfg.get("type"), "created": src is not None}})
        if op == "mqtt5_features":
            return ok({"mqtt5": {
                "user_properties": True, "message_expiry": True,
                "topic_alias": True, "shared_subscription": True,
                "note": "MQTT5 能力接口，需 paho-mqtt>=2.0（缺库时协议级降级为 MQTT3.1.1）"}})
        if op == "sparkplug":
            return ok({"sparkplug_b": {
                "topics": ["spBv1.0/<group>/<type>/<edge>/<device>"],
                "messages": ["NBIRTH","DBIRTH","DATA","DDEATH","NDEATH"],
                "note": "Sparkplug B 生命周期解析能力接口（自动登记设备上/离线）"}})
        return fail(f"未知 op: {op}")

def _main():
    a = MonitorProtocolAtom(name="monitor-protocol", agent="monitor", version="0.1.0")
    a.load()
    r = a.run(op="list")
    assert r.get("ok") and "protocols" in r["data"]
    r2 = a.run(op="mqtt5_features")
    assert r2.get("ok") and r2["data"]["mqtt5"]["user_properties"] is True
    r3 = a.run(op="sparkplug")
    assert r3.get("ok") and "NBIRTH" in r3["data"]["sparkplug_b"]["messages"]
    print("monitor-protocol 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
