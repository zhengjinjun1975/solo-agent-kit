# -*- coding: utf-8 -*-
"""fde-task — 现场 D0-D4 工具箱 + 工单运维原子（增强 support/ops/task）。

工单状态机 + 审计轨迹在原子 _impl/；严重度规则来自 kernels.rules。
可选吃 monitor-device 的 alerts（经 run_flow $ref）。
不 import solo.factory，单原子可独立运行。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402
from kernels import rules as rules_kernel  # noqa: E402


def _now():
    return datetime.now().isoformat(timespec="seconds")


class TicketStore:
    """工单存储 + 状态机（open→diagnosed→resolved→verified→closed）。"""

    _ALLOWED = {
        "open": {"diagnosed", "resolved", "cancelled"},
        "diagnosed": {"resolved", "cancelled"},
        "resolved": {"verified", "closed", "reopened"},
        "verified": {"closed"},
        "reopened": {"diagnosed"},
    }

    def __init__(self, dir):
        self.dir = dir or os.path.join(os.path.expanduser("~"), ".solo", "tickets")
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "tickets.json")
        self._seq = 0

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self, tickets):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(tickets, f, ensure_ascii=False, indent=2)

    def issue(self, problem, severity="medium"):
        tickets = self._load()
        self._seq = len(tickets) + 1
        t = {"id": f"TK-{self._seq:03d}", "problem": problem, "severity": severity,
             "state": "open", "audit": [{"ts": _now(), "event": "issue",
                                         "note": f"创建工单 {severity}"}],
             "diagnosis": None, "resolution": None}
        tickets.append(t)
        self._save(tickets)
        return t

    def _get(self, tid):
        tickets = self._load()
        return next((t for t in tickets if t.get("id") == tid), None), tickets

    def transition(self, tid, target, note=""):
        t, tickets = self._get(tid)
        if not t:
            return None, tickets, "工单不存在"
        cur = t.get("state")
        if target not in self._ALLOWED.get(cur, set()):
            return t, tickets, f"非法转移: {cur} → {target}"
        t["state"] = target
        t.setdefault("audit", []).append({"ts": _now(), "event": target, "note": note})
        self._save(tickets)
        return t, tickets, None

    def diagnose(self, tid, diagnosis):
        t, tickets = self._get(tid)
        if not t:
            return None, "工单不存在"
        t["diagnosis"] = diagnosis
        t.setdefault("audit", []).append({"ts": _now(), "event": "diagnosed",
                                          "note": f"诊断: {diagnosis}"})
        if t["state"] == "open":
            t["state"] = "diagnosed"
        self._save(tickets)
        return t, None

    def resolve(self, tid, resolution):
        t, tickets = self._get(tid)
        if not t:
            return None, "工单不存在"
        t["resolution"] = resolution
        t.setdefault("audit", []).append({"ts": _now(), "event": "resolved",
                                          "note": f"解决: {resolution}"})
        if t["state"] in ("open", "diagnosed"):
            t["state"] = "resolved"
        self._save(tickets)
        return t, None

    def verify(self, tid):
        return self.transition(tid, "verified", "验收通过，工单待关闭")

    def close(self, tid):
        return self.transition(tid, "closed", "工单关闭")

    def audit(self, tid):
        t, _ = self._get(tid)
        if not t:
            return None
        return t.get("audit", [])

    def list(self, state=None):
        tickets = self._load()
        if state:
            tickets = [t for t in tickets if t.get("state") == state]
        return tickets


class FdeTaskAtom(AtomicAgent):
    def capabilities(self):
        return ["fde.task"]

    def inputs(self):
        return {"op": ["issue", "diagnose", "resolve", "verify", "audit", "alarm_tickets", "site"]}

    def _run(self, op="list", dir=None, problem=None, severity="medium", tid=None,
             diagnosis=None, resolution=None, monitor=None, alerts=None, **params):
        try:
            st = TicketStore(dir)
            if op == "issue":
                severity = severity or params.get("severity") or "medium"
                if alerts:
                    severity = rules_kernel.severity_from_alerts(alerts)
                t = st.issue(problem or params.get("problem") or "未命名工单", severity)
                return ok({"ticket": t, "tickets": st.list()})
            if op == "diagnose":
                t, err = st.diagnose(tid or params.get("tid"), diagnosis or "")
                if err:
                    return fail(err)
                return ok({"ticket": t, "tickets": st.list()})
            if op == "resolve":
                t, err = st.resolve(tid or params.get("tid"), resolution or "")
                if err:
                    return fail(err)
                return ok({"ticket": t, "tickets": st.list()})
            if op == "verify":
                t, _, err = st.verify(tid or params.get("tid"))
                if err:
                    return fail(err)
                return ok({"ticket": t, "tickets": st.list()})
            if op == "audit":
                trail = st.audit(tid or params.get("tid"))
                if trail is None:
                    return fail("工单不存在")
                return ok({"audit_trail": trail})
            if op == "alarm_tickets":
                alerts = alerts or params.get("alerts") or []
                made = []
                for a in alerts:
                    sev = a.get("level", "warn")
                    t = st.issue(f"告警: {a.get('message', a.get('device_id', ''))}",
                                 sev)
                    made.append(t)
                return ok({"tickets": made, "created": len(made)})
            if op == "site":
                # 现场台账（轻量）
                return ok({"ticket": {"id": "SITE", "state": "ok",
                                      "note": params.get("note") or "现场运维"}})
            if op == "list":
                return ok({"tickets": st.list()})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"fde-task 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    import tempfile
    a = FdeTaskAtom(name="fde-task", agent="fde")
    a.load()
    d = tempfile.mkdtemp(prefix="task_")
    r = a.run(op="issue", problem="泵振动越限", severity="high", dir=d)
    assert r["ok"] and r["data"]["ticket"]["state"] == "open", "issue 空壳!"
    tid = r["data"]["ticket"]["id"]
    print("ticket:", tid, r["data"]["ticket"]["severity"])
    r2 = a.run(op="diagnose", tid=tid, diagnosis="轴承磨损", dir=d)
    assert r2["ok"] and r2["data"]["ticket"]["state"] == "diagnosed", "diagnose 空壳!"
    r3 = a.run(op="resolve", tid=tid, resolution="更换轴承", dir=d)
    assert r3["ok"] and r3["data"]["ticket"]["state"] == "resolved", "resolve 空壳!"
    r4 = a.run(op="verify", tid=tid, dir=d)
    assert r4["ok"] and r4["data"]["ticket"]["state"] == "verified", "verify 空壳!"
    r5 = a.run(op="audit", tid=tid, dir=d)
    assert r5["ok"] and len(r5["data"]["audit_trail"]) == 4, "audit 留痕缺!"
    print("audit trail:", len(r5["data"]["audit_trail"]))
    r6 = a.run(op="alarm_tickets", alerts=[{"level": "critical", "device_id": "pump_01",
                                            "message": "振动越限"}], dir=d)
    assert r6["ok"] and r6["data"]["created"] == 1
    assert r6["data"]["tickets"][0]["severity"] == "critical", "告警工单严重度错!"
    print("alarm ticket severity:", r6["data"]["tickets"][0]["severity"])
    print("fde-task 独立自测通过")
