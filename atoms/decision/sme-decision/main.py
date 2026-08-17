# -*- coding: utf-8 -*-
"""sme-decision — SME 阈值决策原子（壳→真下沉）。

纯决策规则来自 kernels.rules（run_decisions/阈值深合并）；阈值表 IO 落原子。
可选吃 data-cap 的 SPC 结果作质量决策输入（经 run_flow $ref）。
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
from kernels import rules as rules_kernel  # noqa: E402

_DEFAULT_RULES = os.path.join(_ROOT, "config", "decisions.json")


class SmeDecisionAtom(AtomicAgent):
    def capabilities(self):
        return ["sme.decision"]

    def inputs(self):
        return {"op": ["decide", "set_thresholds", "industry"]}

    def _load_rules(self, rules_path):
        path = rules_path or _DEFAULT_RULES
        if not os.path.exists(path):
            path = _DEFAULT_RULES
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _run(self, op="decide", dir=None, data=None, rules_path=None, model=None,
             industry=None, **params):
        try:
            if op == "decide":
                data = data or params.get("data") or {}
                if isinstance(data, list):
                    data = {"inventory": data}
                rules = self._load_rules(rules_path)
                thresholds = rules.get("_thresholds", {})
                # 行业阈值覆盖（来自 config/industries.json）
                if industry:
                    ind = self._industry_thresholds(industry)
                    if ind:
                        thresholds = rules_kernel.deep_merge_thresholds(thresholds, ind)
                res = rules_kernel.run_decisions(data, rules, thresholds)
                return ok({"decisions": res["decisions"], "thresholds": thresholds,
                           "total": res["total"]})
            if op == "set_thresholds":
                thr = params.get("thresholds") or params.get("thr") or {}
                path = rules_path or _DEFAULT_RULES
                rules = self._load_rules(path)
                rules["_thresholds"] = rules_kernel.deep_merge_thresholds(
                    rules.get("_thresholds", {}), thr)
                if dir:
                    os.makedirs(dir, exist_ok=True)
                    path = os.path.join(dir, "decisions.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(rules, f, ensure_ascii=False, indent=2)
                return ok({"thresholds": rules["_thresholds"]})
            if op == "industry":
                ind = self._industry_thresholds(industry or params.get("industry"))
                return ok({"thresholds": ind or {},
                           "industry": industry or params.get("industry")})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"sme-decision 运行异常: {e}", degraded=True)

    @staticmethod
    def _industry_thresholds(industry):
        if not industry:
            return None
        p = os.path.join(_ROOT, "config", "industries.json")
        if not os.path.exists(p):
            return None
        try:
            with open(p, encoding="utf-8") as f:
                inds = json.load(f)
            entry = inds.get("industries", {}).get(industry) or inds.get(industry)
            if isinstance(entry, dict):
                return entry.get("_thresholds") or {}
        except (json.JSONDecodeError, OSError):
            return None
        return None


if __name__ == "__main__":
    a = SmeDecisionAtom(name="sme-decision", agent="decision")
    a.load()
    data = {
        "inventory": [
            {"product_id": "P001", "stock": 5, "safety_stock": 14, "lead_time_days": 7},
            {"product_id": "P002", "stock": 50, "safety_stock": 14},
        ],
        "sales": [{"product_id": "P001", "qty": 3, "date": "2026-08-01"},
                  {"product_id": "P001", "qty": 4, "date": "2026-08-02"}],
    }
    r = a.run(op="decide", data=data, industry="factory")
    assert r["ok"] and r["data"]["decisions"], "decide 空壳!"
    print("decisions:", len(r["data"]["decisions"]), "total:", r["data"]["total"])
    names = [d["name"] for d in r["data"]["decisions"]]
    assert any("补货" in n or "缺货" in n for n in names), "库存决策未命中!"
    print("rules hit:", sorted(set(names)))
    print("sme-decision 独立自测通过")
