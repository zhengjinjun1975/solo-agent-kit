# -*- coding: utf-8 -*-
"""ontology-qa — 本体建模/聚合问答/知识检索原子（收敛 factory-cognition/monitor-ask）。

纯算法来自 kernels.ontology_core（建模/语义/聚合问答）与 kernels.memory_score（检索排序）。
无 LLM 时走确定性检索内核兜底。不 import solo.factory，单原子可独立运行。
"""
from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402
from kernels import ontology_core as oc  # noqa: E402
from kernels import memory_score  # noqa: E402


class OntologyQaAtom(AtomicAgent):
    def capabilities(self):
        return ["ontology.qa"]

    def inputs(self):
        return {"op": ["build", "semantic", "ask", "retrieve", "link"]}

    def _run(self, op="build", dir=None, rows=None, data=None, question=None,
             top_k=5, industry=None, kb_dir=None, **params):
        try:
            rows = rows if rows is not None else data
            if op == "build":
                rows = rows or []
                entity = params.get("entity_name") or "设备"
                model = oc.build_model(rows, entity_name=entity,
                                       entity_col=params.get("entity_col"))
                if dir:
                    os.makedirs(dir, exist_ok=True)
                    with open(os.path.join(dir, "ontology.json"), "w", encoding="utf-8") as f:
                        json.dump(model, f, ensure_ascii=False, indent=2)
                return ok({"ontology": model})
            if op == "semantic":
                rows = rows or []
                return ok({"semantic": oc.semantic_consistency(rows)})
            if op == "ask":
                rows = rows or []
                q = question or ""
                answer = self._answer(rows, q)
                return ok({"answer": answer})
            if op == "retrieve":
                rows = rows or []
                q = question or ""
                ranked = memory_score.rank_texts(q, [json.dumps(r, ensure_ascii=False)
                                                     for r in rows], top_k=int(top_k or 5))
                return ok({"retrieved": ranked})
            if op == "link":
                rows_a = rows or []
                rows_b = params.get("rows_b") or []
                return ok({"links": oc.link_entities(rows_a, rows_b,
                                                     params.get("key_a", "id"),
                                                     params.get("key_b", "id"))})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"ontology-qa 运行异常: {e}", degraded=True)

    @staticmethod
    def _answer(rows, q):
        """确定性聚合问答：总数/求和/均值/极值/状态过滤。"""
        if not rows:
            return {"hit": False, "answer": "无数据"}
        low = q.lower()
        if "一共" in q or "总共有" in q or "多少条" in q or ("count" in low):
            return {"hit": True, "answer": f"共 {len(rows)} 条记录",
                    "value": len(rows), "kind": "count"}
        # 找数值列求聚合
        num_cols = [c for c in rows[0].keys() if oc.guess_type(rows[0].get(c)) in ("integer", "float")]
        for col in num_cols:
            if "平均" in q or "均值" in q:
                return {"hit": True, "answer": oc.answer_aggregate(rows, col, "avg")}
            if "合计" in q or "总" in q or "求和" in q:
                return {"hit": True, "answer": oc.answer_aggregate(rows, col, "sum")}
            if "最大" in q:
                return {"hit": True, "answer": oc.answer_aggregate(rows, col, "max")}
            if "最小" in q:
                return {"hit": True, "answer": oc.answer_aggregate(rows, col, "min")}
        # 状态/类型过滤
        for c in rows[0].keys():
            vals = {str(r.get(c)) for r in rows}
            for v in list(vals)[:20]:
                if v and v in q:
                    filtered = oc.answer_filter(rows, c, v)
                    if filtered:
                        return {"hit": True,
                                "answer": f"{c}={v} 共 {len(filtered)} 条",
                                "value": len(filtered), "kind": "filter"}
        return {"hit": False, "answer": "未能解析问题，请使用数据类询问（数量/均值/状态）"}


if __name__ == "__main__":
    a = OntologyQaAtom(name="ontology-qa", agent="ontology")
    a.load()
    rows = [{"id": "P001", "status": "运行中", "temp": 80, "power": 100},
            {"id": "P002", "status": "运行中", "temp": 90, "power": 120},
            {"id": "P003", "status": "停机", "temp": 40, "power": 0}]
    r = a.run(op="build", rows=rows, entity_name="设备")
    assert r["ok"] and r["data"]["ontology"]["instances"], "build 空壳!"
    print("instances:", len(r["data"]["ontology"]["instances"]))
    r2 = a.run(op="ask", rows=rows, question="一共有多少条记录")
    assert r2["ok"] and r2["data"]["answer"]["value"] == 3, "count 问答错!"
    print("answer:", r2["data"]["answer"]["answer"])
    r3 = a.run(op="ask", rows=rows, question="温度平均是多少")
    assert r3["ok"] and r3["data"]["answer"]["hit"], "avg 问答空壳!"
    print("avg:", r3["data"]["answer"]["answer"]["value"])
    r4 = a.run(op="ask", rows=rows, question="状态为运行中的设备")
    assert r4["ok"] and r4["data"]["answer"]["value"] == 2, "filter 问答错!"
    print("filter:", r4["data"]["answer"]["answer"])
    print("ontology-qa 独立自测通过")
