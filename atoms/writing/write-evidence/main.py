# -*- coding: utf-8 -*-
"""write-evidence — 写作证据核查原子（证据账本 + 事实核查防幻觉）。

加壳不改核心：复用 legacy `solo/factory/evidence.py` 的 `build_ledger`（从写作产出
提取可证伪声明）与 `fact_check`（与真实数据源比对 → supported/unsupported/contradicted）。
原子只做 op 分发 + {ok,data} 信封，不复制核心算法。

op:
  build_ledger : 从文本提取证据账本（数字/百分比/极值/日期声明）
  fact_check   : 交付前事实核查（声明 × 真实数据源 → 核查报告，防幻觉可溯源）
  report       : 渲染核查结果为人类可读报告
"""
from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402


def _load_evidence():
    """按路径加载 legacy evidence.py（加壳不改核心，独立于 solo.factory 包）。"""
    p = os.path.join(_ROOT, "solo", "factory", "evidence.py")
    spec = importlib.util.spec_from_file_location("write_evidence_legacy", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ev = _load_evidence()


class WriteEvidenceAtom(AtomicAgent):
    def capabilities(self):
        return ["write.evidence"]

    def inputs(self):
        return {"op": ["build_ledger", "fact_check", "report"]}

    def _run(self, op="fact_check", text=None, source_rows=None, col_map=None,
             **params):
        try:
            if op == "build_ledger":
                if not text:
                    return fail("build_ledger 需 text")
                ledger = _ev.build_ledger(text, source_rows=source_rows)
                return ok({"ledger": ledger, "claims_n": len(ledger)})
            if op == "fact_check":
                if not text:
                    return fail("fact_check 需 text")
                result = _ev.fact_check(text, source_rows=source_rows,
                                        col_map=col_map)
                return ok({"report": result, "summary": result.get("summary"),
                           "pass": result.get("pass")})
            if op == "report":
                result = params.get("result")
                if not result:
                    return fail("report 需 result（fact_check 输出）")
                return ok({"report_md": _ev.render_report(result)})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"write-evidence 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    a = WriteEvidenceAtom(name="write-evidence", agent="write")
    a.load()
    text = "温度90度，共5台设备运行正常"
    rows = [{"temperature": 90, "count": 5}, {"temperature": 95, "count": 5}]
    r = a.run(op="fact_check", text=text, source_rows=rows)
    assert r["ok"] and r["data"]["pass"] is not None, "fact_check 空壳!"
    print("summary:", r["data"]["summary"]["verdict"], "pass:", r["data"]["pass"])
    r2 = a.run(op="build_ledger", text=text, source_rows=rows)
    assert r2["ok"] and r2["data"]["claims_n"] >= 1, "build_ledger 空壳!"
    print("claims:", r2["data"]["claims_n"])
    print("write-evidence 独立自测通过")
