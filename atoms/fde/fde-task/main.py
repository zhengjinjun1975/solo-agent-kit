# -*- coding: utf-8 -*-
"""fde-task 原子：FDE 工单状态机/诊断/验收。复用 solo/task.py 核心（零改动）。"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402


def _task_cls():
    from solo import task as _t  # noqa: PLC0415
    return _t.Task


def _default_dir(workdir):
    if workdir:
        return workdir
    import tempfile
    return tempfile.mkdtemp(prefix="fde_task_")


class FdeTaskAtom(AtomicAgent):
    def capabilities(self):
        return ["fde.task"]

    def inputs(self):
        return {"op": "new|issue|diagnose|resolve|status|list|gate",
                "goal/problem/tid/..." : "工单参数"}

    def _run(self, op: str = "list", dir: str = None, **params):
        cls = _task_cls()
        workdir = _default_dir(dir)
        if op == "list":
            return ok({"tickets": cls(workdir).list(state=params.get("state"))})
        if op == "status":
            tid = params.get("tid")
            if not tid:
                return fail("status 需 tid")
            return ok({"status": cls(workdir).status(tid)})
        if op == "new":
            goal = params.get("goal")
            if not goal:
                return fail("new 需 goal")
            return ok({"ticket": cls(workdir).new(goal, tid=params.get("tid"))})
        if op == "issue":
            problem = params.get("problem")
            if not problem:
                return fail("issue 需 problem")
            return ok({"ticket": cls(workdir).new_issue(
                problem, severity=params.get("severity", "medium"))})
        if op == "diagnose":
            tid, diag = params.get("tid"), params.get("diagnosis")
            if not tid or not diag:
                return fail("diagnose 需 tid+diagnosis")
            return ok({"ticket": cls(workdir).diagnose(tid, diag)})
        if op == "resolve":
            tid, res = params.get("tid"), params.get("resolution")
            if not tid or not res:
                return fail("resolve 需 tid+resolution")
            return ok({"ticket": cls(workdir).resolve_issue(tid, res)})
        if op == "gate":
            tid, q = params.get("tid"), params.get("question")
            if not tid or not q:
                return fail("gate 需 tid+question")
            return ok({"gate": cls(workdir).gate(tid, q)})
        if op == "audit":
            tid = params.get("tid")
            if not tid:
                return fail("audit 需 tid")
            return ok({"audit": cls(workdir).issue_audit(tid)})
        return fail(f"未知 op: {op}")


def _main():
    import json
    a = FdeTaskAtom(name="fde-task", agent="fde", version="0.1.0")
    a.load()
    r = a.run(op="new", goal="设备振动异常", dir=None)
    print(json.dumps(r, ensure_ascii=False))
    assert r.get("ok"), "fde-task 独立自测失败"
    r2 = a.run(op="list", dir=None)
    assert r2.get("ok")
    print("fde-task 独立自测通过, 0 失败")


if __name__ == "__main__":
    _main()
