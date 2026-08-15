# -*- coding: utf-8 -*-
"""task.py — 任务状态控制面（断点续跑、决策门、预算）。

方法论（task_state + AHE 决策可观察性）：长任务外置状态，关机不丢；
每次动作带可证伪预期，供下轮验证。零依赖。
"""
from __future__ import annotations

import json
import os
import re

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".solo", "tasks")

STATES = ("todo", "doing", "waiting", "done", "cancelled")


def _slug(s: str) -> str:
    """生成任务 id：保留字母数字/中文/下划线，去特殊字符。"""
    return re.sub(r"[^\w\u4e00-\u9fff\-]", "_", s.strip())[:40] or "task"


class Task:
    """单个任务的外置状态。每个任务一个 JSON 文件。"""

    def __init__(self, dir: str = DEFAULT_DIR):
        self.dir = dir
        os.makedirs(dir, exist_ok=True)

    def _path(self, tid: str) -> str:
        return os.path.join(self.dir, _slug(tid) + ".json")

    def _load(self, tid: str) -> dict:
        try:
            with open(self._path(tid), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self, t: dict) -> None:
        path = self._path(t["id"])
        from solo.base import atomic_write, lock_for
        with lock_for(path):
            atomic_write(path, t)

    def new(self, goal: str, tid: str = None) -> dict:
        """新建任务。tid 可选；默认从 goal 生成。"""
        tid = tid or _slug(goal)
        t = {"id": tid, "goal": goal, "state": "todo", "steps": [],
             "events": [], "gates": [], "prediction": {}, "ts": _now()}
        self._save(t)
        return t

    def new_issue(self, problem: str, severity: str = "medium") -> dict:
        """新建工单（FDE 现场问题闭环 triage→诊断→解决→记录）。

        severity: low/medium/high/critical
        返回工单，含 triage 分类。
        """
        import re as _re
        tid = _slug(problem)[:40] or "issue"
        t = {"id": tid, "problem": problem, "severity": severity,
             "state": "open", "triage": "待诊断", "diagnosis": "",
             "resolution": "", "events": [], "ts": _now()}
        # triage 自动分类（基于关键词，FDE 现场快速分流）
        p = problem.lower()
        if any(k in p for k in ("deploy", "部署", "install", "启动")):
            t["triage"] = "部署类"
        elif any(k in p for k in ("data", "数据", "import", "清洗")):
            t["triage"] = "数据类"
        elif any(k in p for k in ("perf", "性能", "慢", "latency")):
            t["triage"] = "性能类"
        elif any(k in p for k in ("crash", "崩溃", "error", "报错")):
            t["triage"] = "故障类"
        else:
            t["triage"] = "待分类"
        t["audit"] = [{"ts": _now(), "actor": "system", "from": None,
                       "to": "open", "note": f"创建工单({t['triage']})"}]
        t["events"].append({"ts": _now(), "event": f"open({t['triage']})"})
        self._save(t)
        return t

    def diagnose(self, tid: str, diagnosis: str) -> dict:
        """记录诊断（FDE 排障根因分析）。"""
        t = self._load(tid)
        if not t or "problem" not in t:
            return {"error": "issue not found"}
        cur = t.get("state", "open")
        t["diagnosis"] = diagnosis
        t["state"] = "diagnosed"
        t["audit"] = t.get("audit", [])
        t["audit"].append({"ts": _now(), "actor": "user", "from": cur,
                           "to": "diagnosed", "note": "记录诊断"})
        t["events"].append({"ts": _now(), "event": "diagnosed"})
        self._save(t)
        return t

    def resolve_issue(self, tid: str, resolution: str) -> dict:
        """记录解决 + 闭环（FDE 问题闭环）。"""
        t = self._load(tid)
        if not t or "problem" not in t:
            return {"error": "issue not found"}
        cur = t.get("state", "open")
        t["resolution"] = resolution
        t["state"] = "resolved"
        t["audit"] = t.get("audit", [])
        t["audit"].append({"ts": _now(), "actor": "user", "from": cur,
                           "to": "resolved", "note": "记录解决"})
        t["events"].append({"ts": _now(), "event": "resolved"})
        self._save(t)
        return t

    def list_issues(self) -> list:
        """列出所有工单（含闭环状态）。"""
        issues = []
        for fname in os.listdir(self.dir):
            if not fname.endswith(".json"):
                continue
            tid = fname[:-5]
            t = self._load(tid)
            if t and "problem" in t:
                issues.append({"id": t["id"], "problem": t["problem"],
                               "severity": t.get("severity"), "triage": t.get("triage"),
                               "state": t.get("state"), "ts": t.get("ts")})
        return issues

    # ---- 工单状态机 + 审计（P0：借鉴 LangGraph 确定性状态机，工单全生命周期可审计）----
    # 合法状态转移表（确定性，杜绝任意状态乱跳）
    ISSUE_TRANSITIONS = {
        "open": {"in_progress", "diagnosed", "closed", "cancelled"},
        "in_progress": {"diagnosed", "resolved", "closed", "cancelled"},
        "diagnosed": {"in_progress", "resolved", "closed", "cancelled"},
        "resolved": {"closed"},
        "closed": set(),
        "cancelled": set(),
    }

    def issue_audit(self, tid: str) -> dict:
        """工单操作审计：全生命周期操作记录（谁/何时/做了什么/从哪到哪）。"""
        t = self._load(tid)
        if not t or "problem" not in t:
            return {"error": "issue not found", "id": tid}
        return {"id": tid, "problem": t.get("problem"), "state": t.get("state"),
                "audit": t.get("audit", []), "events": t.get("events", [])}

    def transition(self, tid: str, target: str, actor: str = "user",
                   note: str = "") -> dict:
        """工单确定性状态机：合法流转 + 每一步写操作审计。

        actor: 操作者（user / monitor / rule-chain / system）。
        审计记录 = {ts, actor, from, to, note}，append 不可变，构成全生命周期操作轨迹。
        """
        t = self._load(tid)
        if not t or "problem" not in t:
            return {"error": "issue not found", "id": tid}
        cur = t.get("state", "open")
        if target not in self.ISSUE_TRANSITIONS.get(cur, set()):
            return {"error": f"非法流转: {cur} → {target}",
                    "id": tid, "state": cur,
                    "legal": sorted(self.ISSUE_TRANSITIONS.get(cur, set()))}
        t["state"] = target
        t["audit"] = t.get("audit", [])
        t["audit"].append({"ts": _now(), "actor": actor, "from": cur,
                           "to": target, "note": note})
        t["events"].append({"ts": _now(), "event": f"{target}({actor})",
                            "note": note})
        if target == "closed":
            t["closed_at"] = _now()
        self._save(t)
        return {"id": tid, "state": target, "from": cur, "to": target,
                "audit_count": len(t["audit"]), "audit": t["audit"]}

    def reopen(self, tid: str, actor: str = "user", note: str = "") -> dict:
        """重开工单（closed → open，合法单向往返，审计记录）。"""
        return self.transition(tid, "open", actor=actor, note=note)

    def status(self, tid: str) -> dict:
        t = self._load(tid)
        if not t:
            return {"error": "task not found", "id": tid}
        return t

    def set_state(self, tid: str, state: str, note: str = "") -> dict:
        t = self._load(tid)
        if not t:
            return {"error": "task not found"}
        t["state"] = state
        if note:
            t["events"].append({"ts": _now(), "event": f"state->{state}", "note": note})
        self._save(t)
        return t

    def add_step(self, tid: str, text: str) -> dict:
        t = self._load(tid)
        if not t:
            return {"error": "task not found"}
        t["steps"].append({"text": text, "done": False, "ts": _now()})
        self._save(t)
        return t

    def gate(self, tid: str, question: str) -> dict:
        """决策门：记录一个待确认问题，返回 gate 状态。"""
        t = self._load(tid)
        if not t:
            return {"error": "task not found"}
        t["gates"].append({"question": question, "resolved": False, "ts": _now()})
        t["state"] = "waiting"
        self._save(t)
        return {"id": tid, "gate": question, "state": "waiting"}

    def resolve(self, tid: str) -> dict:
        """解决所有待确认门。"""
        t = self._load(tid)
        if not t:
            return {"error": "task not found"}
        for g in t["gates"]:
            g["resolved"] = True
        t["state"] = "doing"
        self._save(t)
        return {"id": tid, "state": "doing"}

    def predict(self, tid: str, claim: str) -> dict:
        """可证伪预期（AHE 决策可观察性）：记录'我预期这会让X更好'。"""
        t = self._load(tid)
        if not t:
            return {"error": "task not found"}
        t["prediction"] = {"claim": claim, "made": _now(), "verified": False}
        self._save(t)
        return t["prediction"]

    def verify_prediction(self, tid: str, outcome: bool) -> dict:
        t = self._load(tid)
        if not t:
            return {"error": "task not found"}
        t["prediction"]["verified"] = outcome
        self._save(t)
        return t["prediction"]

    def list(self, state: str = None) -> list:
        out = []
        for fn in os.listdir(self.dir):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(self.dir, fn), encoding="utf-8") as f:
                        t = json.load(f)
                    if state is None or t.get("state") == state:
                        out.append({"id": t["id"], "goal": t["goal"][:40], "state": t["state"]})
                except Exception:
                    continue
        return out


def _now() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")
