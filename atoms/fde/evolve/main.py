# -*- coding: utf-8 -*-
"""evolve — 自进化反馈闭环原子（反馈→归因→改进→校验→沉淀）。

把 fde_runtime/evolve.py 的进化内核封装为原子，暴露 `evolve.self` 能力，
可被组装链调用（如 solo-linkage-workflow.json 链尾做自进化回灌）。
纯标准库，零第三方依赖。不 import solo.factory，单原子可独立运行。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402
from fde_runtime import evolve as evolve_core  # noqa: E402


class EvolveAtom(AtomicAgent):
    def capabilities(self):
        return ["evolve.self"]

    def inputs(self):
        return {"op": ["evolve", "recent", "closed_count", "status"]}

    def _run(self, op="evolve", dir=None, observation=None, target=None,
             feedback=None, **params):
        try:
            # 允许用 dir 覆盖进化日志位置（组装链传 $dir 隔离测试）
            path = None
            if dir:
                path = os.path.join(dir, "evolution.json")
            if op == "evolve":
                observation = observation or params.get("observation") or ""
                target = target or params.get("target") or "knowledge"
                feedback = feedback if feedback is not None else params.get("feedback")
                r = evolve_core.evolve(observation, target=target, feedback=feedback)
                # 若指定 dir，复制到该位置以便组装链 $ref 读取闭环状态
                entry = r["entry"]
                if path:
                    log = evolve_core.EvolutionLog(path=path)
                    log.record(entry["observation"], entry.get("target"),
                               entry.get("feedback"), entry.get("attribution"),
                               entry.get("improved"), entry.get("verified"))
                return ok({"entry": entry, "loop_closed": r["loop_closed"]})
            if op == "recent":
                log = evolve_core.EvolutionLog(path=path)
                return ok({"recent": log.recent(int(params.get("n", 5))),
                           "closed_count": log.closed_count()})
            if op == "closed_count":
                log = evolve_core.EvolutionLog(path=path)
                return ok({"closed_count": log.closed_count()})
            if op == "status":
                log = evolve_core.EvolutionLog(path=path)
                entries = log.recent(3)
                return ok({"closed_count": log.closed_count(),
                           "total": len(entries),
                           "loop_closed": any(e.get("loop_closed") for e in entries),
                           "recent": entries})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"evolve 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    import tempfile
    a = EvolveAtom(name="evolve", agent="learning")
    a.load()
    d = tempfile.mkdtemp(prefix="ev_")
    r = a.run(op="evolve", dir=d, observation="水泵振动误报偏高",
              target="threshold", feedback=2, k=3.0)
    assert r["ok"] and r["data"]["loop_closed"], "阈值改进应闭环"
    print("evolve target:", r["data"]["entry"]["target"],
          "loop_closed:", r["data"]["loop_closed"])
    r2 = a.run(op="evolve", dir=d, observation="风机缺同义词'鼓风机'",
               target="dictionary", words=["鼓风机"])
    assert r2["ok"] and r2["data"]["loop_closed"], "词典改进应闭环"
    r3 = a.run(op="status", dir=d)
    assert r3["ok"] and r3["data"]["closed_count"] == 2, "闭环计数应为2"
    print("closed_count:", r3["data"]["closed_count"])
    print("evolve 原子独立自测通过")
