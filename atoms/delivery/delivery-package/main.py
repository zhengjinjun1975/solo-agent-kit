# -*- coding: utf-8 -*-
"""delivery-package 原子：一键交付包（监测快照 + 工单 + 交付报告 + 验收清单）。

复用 solo/factory/assist.py report_draft/report_draft_dict（对齐闭源 deliver 字段，solo_draft:true）。
"""
from __future__ import annotations
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402

def _a():
    from solo.factory import assist as _m  # noqa: PLC0415
    return _m

class DeliveryPackageAtom(AtomicAgent):
    def capabilities(self):
        return ["delivery.package"]
    def _run(self, op: str = "report", **params):
        mod = _a()
        hit = params.get("hit", 0.9)
        questions_n = params.get("questions_n", 0)
        hits = params.get("hits", 0)
        if op == "report":
            md, ai = mod.report_draft(
                kb=params.get("kb"), industry=params.get("industry"), hit=hit,
                questions_n=questions_n, hits=hits,
                asset_versions=params.get("asset_versions", 0),
                health=params.get("health"), note=params.get("note"))
            return ok({"markdown": md, "ai": ai})
        if op == "report_dict":
            d = mod.report_draft_dict(
                kb=params.get("kb"), industry=params.get("industry"), hit=hit,
                questions_n=questions_n, hits=hits,
                asset_versions=params.get("asset_versions", 0),
                health=params.get("health"), baseline=params.get("baseline"),
                note=params.get("note"))
            return ok({"report": d})
        if op == "package":
            # 一键交付包：监测快照 + 工单 + 交付报告 + 验收清单
            snap = params.get("monitor_snapshot") or {}
            tickets = params.get("tickets") or []
            report = mod.report_draft_dict(
                kb=params.get("kb"), industry=params.get("industry"), hit=hit,
                questions_n=questions_n, hits=hits,
                asset_versions=params.get("asset_versions", 0),
                health=params.get("health"), baseline=params.get("baseline"),
                note=params.get("note"))
            accept = {
                "acceptance_list": [
                    {"item": "监测快照", "pass": bool(snap)},
                    {"item": "工单闭环", "pass": bool(tickets)},
                    {"item": "交付报告", "pass": bool(report)},
                ],
                "signed": params.get("signed", False),
            }
            return ok({"package": {
                "monitor_snapshot": snap, "tickets": tickets,
                "report": report, "acceptance": accept,
                "solo_draft": True}})
        return fail(f"未知 op: {op}")

def _main():
    a = DeliveryPackageAtom(name="delivery-package", agent="deliver", version="0.1.0")
    a.load()
    r = a.run(op="report_dict", hit=0.9, questions_n=10, hits=9,
              kb="factory", industry="factory", baseline=0.7)
    assert r.get("ok") and r["data"]["report"]["solo_draft"] is True, "report_dict 失败"
    r2 = a.run(op="package", monitor_snapshot={"devices": 2}, tickets=[{"id": "TK-1"}],
               hit=0.9, questions_n=10, hits=9)
    assert r2.get("ok") and r2["data"]["package"]["acceptance"]["acceptance_list"][0]["pass"], "package 失败"
    print("delivery-package 独立自测通过, 0 失败")

if __name__ == "__main__":
    _main()
