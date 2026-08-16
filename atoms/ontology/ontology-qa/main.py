# -*- coding: utf-8 -*-
"""ontology-qa 原子：本体建模/问答。复用 solo/factory/ontology Ontology 核心(零改动)。"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _o():
    from solo.factory.ontology import Ontology  # noqa: PLC0415
    return Ontology

class OntologyQaAtom(AtomicAgent):
    def capabilities(self):
        return ["ontology.qa"]
    def _run(self, op: str = "build", **params):
        cls = _o()
        ont = cls(col_cn=params.get("col_cn"))
        if op == "build":
            rows = params.get("rows")
            if rows is None:
                return fail("build 需 rows")
            ont.from_rows(rows, entity_name=params.get("entity_name"))
            ont.build()
            return ok({"built": len(ont.entities)})
        if op == "ask":
            rows = params.get("rows")
            if rows is not None:
                ont.from_rows(rows, entity_name=params.get("entity_name"))
                ont.build()
            q = params.get("question")
            if not q:
                return fail("ask 需 question")
            return ok({"answer": ont.answer(q)})
        return fail(f"未知 op: {op}")

def _main():
    a = OntologyQaAtom(name="ontology-qa", agent="ontology", version="0.1.0")
    a.load()
    rows = [{"设备": "水泵A", "状态": "运行中"}, {"设备": "水泵B", "状态": "停机"}]
    r = a.run(op="build", rows=rows)
    assert r.get("ok"), "ontology build 失败"
    r2 = a.run(op="ask", rows=rows, question="有几台设备运行中")
    assert r2.get("ok"), "ontology ask 失败"
    print("ontology-qa 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
