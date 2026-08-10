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
    return re.sub(r"[^A-Za-z0-9_-]", "_", s.strip())[:40] or "task"


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
        with open(self._path(t["id"]), "w", encoding="utf-8") as f:
            json.dump(t, f, ensure_ascii=False, indent=1)

    def new(self, goal: str, tid: str = None) -> dict:
        """新建任务。tid 可选；默认从 goal 生成。"""
        tid = tid or _slug(goal)
        t = {"id": tid, "goal": goal, "state": "todo", "steps": [],
             "events": [], "gates": [], "prediction": {}, "ts": _now()}
        self._save(t)
        return t

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
