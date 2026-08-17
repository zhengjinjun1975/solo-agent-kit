# -*- coding: utf-8 -*-
"""diagnose-kb — 故障诊断知识库原子（增强 support.KnowledgeBase）。

知识条目存储 IO 在原子 _impl/；相似检索来自 kernels.memory_score，故障映射来自 kernels.rules。
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
from kernels import memory_score  # noqa: E402


class _KbStore:
    def __init__(self, dir):
        self.dir = dir or os.path.join(os.path.expanduser("~"), ".solo", "kb")
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "kb.json")

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def add(self, problem, solution, signals=None):
        entries = self._load()
        entries.append({"problem": problem, "solution": solution,
                        "signals": signals or []})
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        return entries

    def all(self):
        return self._load()


class DiagnoseKbAtom(AtomicAgent):
    def capabilities(self):
        return ["diagnose.kb"]

    def inputs(self):
        return {"op": ["add", "query", "search", "train", "suggest"]}

    def _run(self, op="search", dir=None, problem=None, fault=None, kb=None,
             industry=None, rows=None, solution=None, top_k=3, **params):
        try:
            store = _KbStore(dir)
            if op == "add":
                problem = problem or params.get("problem")
                solution = solution or params.get("solution")
                if not problem or not solution:
                    return fail("add 需要 problem 与 solution")
                store.add(problem, solution, params.get("signals"))
                return ok({"hit": {"problem": problem, "solution": solution}})
            if op in ("query", "search"):
                q = problem or fault or params.get("q") or ""
                entries = store.all()
                texts = [e.get("problem", "") for e in entries]
                ranked = memory_score.rank_texts(q, texts, top_k=int(top_k or 3))
                matches = []
                for r in ranked:
                    if r["score"] < 0.1:
                        continue
                    e = entries[r["index"]]
                    matches.append({**r, "solution": e.get("solution", ""),
                                    "signals": e.get("signals", [])})
                if matches:
                    best = matches[0]
                    return ok({"hit": best, "answer": best["solution"],
                               "matches": matches})
                return ok({"hit": None, "answer": None, "matches": [],
                           "note": "知识库无匹配，诚实 miss"})
            if op == "train":
                # 从历史工单/故障行沉淀知识
                rows = rows or params.get("rows") or []
                for r in rows:
                    if r.get("problem") and r.get("solution"):
                        store.add(r["problem"], r["solution"], r.get("signals"))
                return ok({"hit": {"trained_n": len(rows)},
                           "suggestions": []})
            if op == "suggest":
                from kernels.forecast import fault_advice
                q = problem or fault or params.get("problem") or ""
                advice = fault_advice(q)
                return ok({"suggestions": advice.get("actions", []),
                           "hit": {"actions": advice.get("actions", []),
                                   "parts": advice.get("parts", []),
                                   "estimated_cost": advice.get("estimated_cost", 0)}})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"diagnose-kb 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    import tempfile
    a = DiagnoseKbAtom(name="diagnose-kb", agent="diagnose")
    a.load()
    d = tempfile.mkdtemp(prefix="kb_")
    r = a.run(op="add", problem="泵振动越限", solution="检查轴承与对中",
              signals=["vibration"], dir=d)
    assert r["ok"], "add 空壳!"
    r2 = a.run(op="search", problem="泵振动偏高", top_k=3, dir=d)
    assert r2["ok"] and r2["data"]["hit"], "search 空壳!"
    print("kb hit solution:", r2["data"]["hit"]["solution"], "score:", r2["data"]["hit"]["score"])
    r3 = a.run(op="suggest", problem="振动越限", dir=d)
    assert r3["ok"] and r3["data"]["suggestions"], "suggest 空壳!"
    print("suggestions:", r3["data"]["suggestions"])
    r4 = a.run(op="search", problem="完全无关内容xyz", dir=d)
    assert r4["data"]["hit"] is None, "未诚实 miss!"
    print("diagnose-kb 独立自测通过")
