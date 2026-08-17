# -*- coding: utf-8 -*-
"""deliver-accept — 交付验收闭环原子（需求→SRS→验收→勾稽→交付包→签收）。【唯一闭源】

纯算法来自 kernels.survey_core（访谈提纲/需求结构化/生成SRS/验收清单/勾稽/报告草稿）；
有状态交付编排+IO 落此原子。open_source:false，闭源增值逻辑不外泄。
可选吃 monitor_snapshot(monitor-device) / tickets(fde-task) 输出（经 run_flow $ref）。
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


def _norm_req(requirements):
    """输入需求可为 dict{...}（SRS 条目）或 list[dict]。统一为 list[dict]。"""
    if isinstance(requirements, dict):
        return list(requirements.get("requirements") or [])
    return list(requirements or [])


class DeliverAcceptAtom(AtomicAgent):
    def capabilities(self):
        return ["deliver.accept"]

    def inputs(self):
        return {"op": ["outline", "requirement", "srs", "acceptance",
                       "reconcile", "package", "verify"]}

    def _run(self, op="package", dir=None, story=None, requirements=None,
             title=None, monitor_snapshot=None, tickets=None, acceptance=None,
             **params):
        try:
            reqs = _norm_req(requirements)
            if op == "outline":
                industry = params.get("industry") or "factory"
                out = survey_core.interview_outline(
                    industry, entity_cn=params.get("entity_cn", "设备"),
                    measure=params.get("measure", "台"),
                    note=params.get("note", ""))
                return ok({"outline": out})
            if op == "requirement":
                if not story:
                    return fail("requirement 需 story（用户故事/痛点）")
                try:
                    r = survey_core.structure_requirement(
                        story, category=params.get("category", "生产"),
                        priority=params.get("priority", "P2"),
                        acceptance=params.get("acceptance"),
                        title=params.get("req_title"), req_id=params.get("req_id", "R-001"))
                except ValueError as e:
                    return fail(f"需求参数非法: {e}")
                self._save(dir, "requirement.json", r)
                return ok({"requirement": r})
            if op == "srs":
                if not reqs:
                    return fail("srs 需 requirements")
                srs = survey_core.generate_srs(reqs, title=title or "需求规格说明书")
                self._save(dir, "srs.md", srs["markdown"])
                return ok({"srs": srs, "req_n": srs["req_n"]})
            if op == "acceptance":
                if not reqs:
                    return fail("acceptance 需 requirements")
                lst = survey_core.build_acceptance(reqs)
                self._save(dir, "acceptance.json", lst)
                return ok({"acceptance_list": lst})
            if op == "reconcile":
                acc = acceptance or survey_core.build_acceptance(reqs)
                rec = survey_core.reconcile(reqs, acc)
                return ok({"reconcile": rec, "acceptance_list": acc})
            if op == "package":
                # 交付包：SRS + 验收清单 + 监测快照 + 工单 + 交付报告（勾稽一致）
                reqs = reqs or params.get("reqs") or []
                if not reqs:
                    # 允许用已结构化的 acceptance 兜底
                    pass
                lst = acceptance or (survey_core.build_acceptance(reqs) if reqs else [])
                rec = survey_core.reconcile(reqs, lst) if reqs else {"ok": True}
                acc_status = survey_core.reconcile_acceptance(lst)
                report = survey_core.report_draft(
                    kb=params.get("kb"), industry=params.get("industry", "factory"),
                    hit=params.get("hit", 0.0),
                    questions_n=params.get("questions_n", 0),
                    hits=params.get("hits", 0),
                    title=params.get("report_title", "FDE 交付报告"))
                pkg = {
                    "monitor_snapshot": monitor_snapshot or {},
                    "tickets": tickets or [],
                    "report": report, "reconcile": rec,
                    "acceptance": {"acceptance_list": lst, **acc_status},
                }
                self._save(dir, "delivery_package.json",
                           {"report_md": report.get("markdown", "")})
                return ok({"package": pkg, "reconcile": rec, "accept": acc_status})
            if op == "verify":
                lst = acceptance or (survey_core.build_acceptance(reqs) if reqs else [])
                acc = survey_core.reconcile_acceptance(lst)
                return ok({"accept": acc, "acceptance_list": lst})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"deliver-accept 运行异常: {e}", degraded=True)

    @staticmethod
    def _save(dir, name, data):
        if not dir:
            return
        os.makedirs(dir, exist_ok=True)
        with open(os.path.join(dir, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import tempfile
    a = DeliverAcceptAtom(name="deliver-accept", agent="deliver",
                          open_source=False, license="closed")
    a.load()
    d = tempfile.mkdtemp(prefix="del_")
    # 需求 → SRS → 验收 → 勾稽 → 交付包 → verify
    r1 = a.run(op="requirement", story="SPC 判异能力上线，实现振动越限自动预警",
               category="质量", priority="P0", req_id="R-001", dir=d)
    assert r1["ok"] and r1["data"]["requirement"]["id"] == "R-001", "requirement 空壳!"
    r2 = a.run(op="requirement", story="设备监测看板，支持实时振动趋势",
               category="设备", priority="P1", req_id="R-002", dir=d)
    assert r2["ok"], "requirement2 空壳!"
    reqs = [r1["data"]["requirement"], r2["data"]["requirement"]]
    s = a.run(op="srs", requirements=reqs, title="泵站运维系统SRS", dir=d)
    assert s["ok"] and s["data"]["srs"]["req_n"] == 2, "srs 空壳!"
    print("srs req_n:", s["data"]["srs"]["req_n"])
    acc = a.run(op="acceptance", requirements=reqs, dir=d)
    assert acc["ok"] and len(acc["data"]["acceptance_list"]) >= 2, "acceptance 空壳!"
    lst = acc["data"]["acceptance_list"]
    for i in lst:
        i["result"] = "通过"
    rec = a.run(op="reconcile", requirements=reqs, acceptance=lst, dir=d)
    assert rec["ok"] and rec["data"]["reconcile"]["ok"], "勾稽未通过!"
    print("reconcile ok:", rec["data"]["reconcile"]["ok"])
    pkg = a.run(op="package", requirements=reqs, acceptance=lst,
                monitor_snapshot={"devices": 2},
                tickets=[{"id": "TK-001"}], kb="factory", dir=d)
    assert pkg["ok"] and pkg["data"]["package"]["acceptance"]["acceptance_list"], "package 空壳!"
    assert pkg["data"]["package"]["report"]["markdown"], "交付报告空壳!"
    v = a.run(op="verify", acceptance=lst, dir=d)
    assert v["ok"] and v["data"]["accept"]["accept"] is True, "verify 未全过!"
    print("accept:", v["data"]["accept"])
    print("deliver-accept 独立自测通过（闭源原子，license=closed）")
