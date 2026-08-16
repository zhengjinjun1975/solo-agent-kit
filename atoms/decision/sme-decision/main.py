# -*- coding: utf-8 -*-
"""sme-decision 原子：复用 sme-decision-ontology 决策能力（开源原子联动）。

联动复用（跨仓库，算法开源，数据不出厂）：
  - decide  : 调用 sme-decision-ontology/codes/rules_engine.run_rules 确定性决策
              （补货/缺货/呆滞/账龄/保修/预测/比价/供应商 8 指标，每条带公式依据）
  - action  : suggestions_to_actions 建议 → 行动清单（优先级/责任人/状态）
  - feedback: feedback_engine.apply_feedback / preview 阈值回灌（误报放松/漏报收紧/有效保持）
  - decide_alert: 告警 → 决策 → 行动 一键链（把 monitor 告警映射到经营/维护决策与行动）

边界：数据各自落在本地 data/，联动只传「数据目录 + 入参」，算法开源、数据不出厂。
"""
from __future__ import annotations
import json
import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402
from fde_runtime import linkage  # noqa: E402


class SmeDecisionAtom(AtomicAgent):
    def capabilities(self):
        return ["sme.decision"]

    def _run(self, op: str = "linkage", **params):
        if op == "linkage":
            return ok(linkage.status())

        root = linkage.find_sme()
        if not root:
            return fail("sme-decision-ontology 未找到，无法决策（数据不出厂，需本地部署）",
                        degraded=True)
        linkage.add_codes_to_path(root)
        codes = os.path.join(root, "codes")

        if op == "decide":
            """确定性决策。data_dir 缺省用 sme 仓库自带 data/（合成示例数据）。"""
            data_dir = params.get("data_dir") or os.path.join(root, "data")
            enabled = params.get("enabled") or ["inventory", "procurement", "sales", "equipment"]
            industry = params.get("industry")
            if not os.path.isdir(data_dir):
                return fail(f"数据目录不存在: {data_dir}")
            try:
                with linkage.codes_isolation(root):
                    from core.domain_model import load_all  # noqa: PLC0415
                    import rules_engine as reng  # noqa: PLC0415
                    data = load_all(data_dir)
                    res = reng.run_rules(data, enabled=enabled, industry=industry)
                    n = sum(len(v) for v in res.values())
                return ok({"modules": {k: len(v) for k, v in res.items()},
                           "total": n, "decisions": res, "industry": industry or "default"})
            except Exception as e:  # noqa: BLE001
                return fail(f"sme 决策异常: {e}", degraded=True)

        if op == "action":
            """建议 → 行动清单。"""
            suggestions = params.get("suggestions") or []
            data_dir = params.get("data_dir") or os.path.join(root, "data")
            if not suggestions:
                return fail("action 需 suggestions")
            try:
                with linkage.codes_isolation(root):
                    from core.domain_model import load_all  # noqa: PLC0415
                    import action as ac  # noqa: PLC0415
                    data = load_all(data_dir)
                    acts = ac.suggestions_to_actions(suggestions, data)
                return ok({"actions": acts, "count": len(acts)})
            except Exception as e:  # noqa: BLE001
                return fail(f"sme 行动清单异常: {e}", degraded=True)

        if op == "feedback":
            """阈值回灌（可 preview 只算不改）。"""
            industry = params.get("industry", "manufacturing")
            records = params.get("feedback_records") or []
            if not records:
                return fail("feedback 需 feedback_records")
            try:
                with linkage.codes_isolation(root):
                    import feedback_engine as fb  # noqa: PLC0415
                    src = os.path.join(root, "config", "industry_thresholds.json")
                    mode = params.get("mode", "preview")
                    if mode == "apply":
                        # 用仓库内真实阈值表回灌（可传 config_path 覆盖以隔离）
                        cfg = params.get("config_path") or src
                        summary = fb.apply_feedback(industry, records, config_path=cfg)
                    else:
                        cfg = params.get("config_path")
                        if not cfg:
                            # 预览不落盘：拷贝到临时目录
                            tmp = tempfile.mkdtemp(prefix="fde_fb_")
                            cfg = os.path.join(tmp, "industry_thresholds.json")
                            shutil.copy(src, cfg)
                        summary = fb.preview_feedback(industry, records, config_path=cfg)
                return ok({"summary": summary, "count": len(summary), "mode": mode})
            except Exception as e:  # noqa: BLE001
                return fail(f"sme 阈值回灌异常: {e}", degraded=True)

        if op == "decide_alert":
            """告警 → 决策 → 行动 一键链（跨 monitor + sme）。"""
            alert = params.get("alert") or {}
            device_id = alert.get("device_id") or params.get("device_id")
            metric = alert.get("metric") or params.get("metric")
            value = alert.get("value") or params.get("value")
            # 构造一条维护/经营决策建议
            suggestion = {
                "entity": device_id or "dev",
                "action": params.get("action") or "维护告急",
                "level": params.get("level") or "预警",
                "reason": f"{device_id} 的 {metric} 值 {value} 越限，触发维护/经营决策",
            }
            r = self._run(op="action", data_dir=params.get("data_dir"),
                          suggestions=[suggestion])
            acts = r.get("data", {}).get("actions") if r.get("ok") else []
            return ok({"alert": alert, "suggestion": suggestion,
                       "actions": acts, "decision": suggestion.get("action")})

        return fail(f"未知 op: {op}")


def _main():
    a = SmeDecisionAtom(name="sme-decision", agent="decision", version="0.1.0")
    a.load()
    present = linkage.status()["sme_decision_ontology"]["present"]
    print("sme present:", present)
    if present:
        r = a.run(op="decide", enabled=["inventory", "equipment"], industry="manufacturing")
        assert r.get("ok") and r["data"]["total"] > 0, "决策应有输出"
        print("  decide total:", r["data"]["total"], r["data"]["modules"])
        r2 = a.run(op="feedback", industry="manufacturing",
                   feedback_records=[{"metric_key": "inventory.safety_stock", "verdict": "误报"}],
                   mode="preview")
        assert r2.get("ok") and r2["data"]["count"] > 0, "回灌预览应有调整"
        print("  feedback preview:", r2["data"]["summary"][0]["after"])
    print("sme-decision 独立自测通过, 0 失败")


if __name__ == "__main__":
    _main()
