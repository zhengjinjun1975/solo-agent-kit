# -*- coding: utf-8 -*-
"""deliver-train — 知识转移/培训原子（操作手册 + FAQ + 知识转移清单）。

纯算法来自 kernels.survey_core（manual/faq/transfer_checklist）。
入参 requirements/srs 可来自 deliver-accept 输出（经 run_flow $ref）。
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
from kernels import survey_core  # noqa: E402


class DeliverTrainAtom(AtomicAgent):
    def capabilities(self):
        return ["deliver.train"]

    def inputs(self):
        return {"op": ["manual", "faq", "transfer"]}

    def _run(self, op="manual", dir=None, capabilities=None, requirements=None,
             questions=None, title=None, srs=None, **params):
        try:
            reqs = requirements or (srs or {}).get("requirements") or []
            if op == "manual":
                man = survey_core.manual(capabilities or params.get("caps") or {},
                                         reqs or None, title or "系统操作手册")
                self._save(dir, "manual.md", man["markdown"])
                return ok({"manual": man})
            if op == "faq":
                fq = survey_core.faq(questions or params.get("questions") or None,
                                     title or "常见问题 FAQ")
                self._save(dir, "faq.md", fq["markdown"])
                return ok({"faq": fq})
            if op == "transfer":
                tcl = survey_core.transfer_checklist(reqs, title or "知识转移清单")
                self._save(dir, "transfer_checklist.json", tcl)
                return ok({"transfer_checklist": tcl})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"deliver-train 运行异常: {e}", degraded=True)

    @staticmethod
    def _save(dir, name, data):
        if not dir:
            return
        os.makedirs(dir, exist_ok=True)
        with open(os.path.join(dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import tempfile
    a = DeliverTrainAtom(name="deliver-train", agent="deliver")
    a.load()
    d = tempfile.mkdtemp(prefix="train_")
    reqs = [
        {"id": "R-001", "title": "SPC 判异", "category": "质量",
         "story": "SPC 判异能力上线", "priority": "P0",
         "acceptance": ["SPC判异可观测"]},
        {"id": "R-002", "title": "振动预警", "category": "设备",
         "story": "振动越限自动预警", "priority": "P1",
         "acceptance": ["振动预警可观测"]},
    ]
    caps = {"监测": {"SPC图": {"desc": "过程能力控制图"},
                     "看板": {"desc": "实时振动趋势"}}}
    m = a.run(op="manual", capabilities=caps, requirements=reqs,
              title="泵站运维培训", dir=d)
    assert m["ok"] and m["data"]["manual"]["markdown"], "manual 空壳!"
    print("manual sections:", m["data"]["manual"]["sections"],
          "steps:", m["data"]["manual"]["steps"])
    f = a.run(op="faq", title="泵站运维FAQ", dir=d)
    assert f["ok"] and f["data"]["faq"]["count"] >= 3, "faq 空壳!"
    print("faq count:", f["data"]["faq"]["count"])
    t = a.run(op="transfer", requirements=reqs, dir=d)
    assert t["ok"] and len(t["data"]["transfer_checklist"]) == 2, "transfer 空壳!"
    print("transfer items:", len(t["data"]["transfer_checklist"]))
    print("deliver-train 独立自测通过")
