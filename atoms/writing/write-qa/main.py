# -*- coding: utf-8 -*-
"""write-qa — 写作质量检查原子（六维 D1-D6 + AI味检测）。

加壳不改核心：复用 legacy `solo/writing.py` 的 `scan`（六维中文写作质量检查）
与 `ai_taste`（AI 味自检/证据核查入口），原子只做 op 分发 + {ok,data} 信封。
不复制核心算法，单原子可独立运行（A3 铁律）。

op:
  scan      : 六维检查（D1错字/D2标点/D3语病/D4数字/D5去AI味/D6活人感）
  ai_taste  : AI 味自检（分 100=最像人 + 可执行改写建议）
  styles    : 可用写作风格清单（tweet/report/wechat/paper）
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fde_runtime.base import AtomicAgent, ok, fail  # noqa: E402
from solo import writing  # noqa: E402


class WriteQaAtom(AtomicAgent):
    def capabilities(self):
        return ["write.qa"]

    def inputs(self):
        return {"op": ["scan", "ai_taste", "styles"]}

    def _run(self, op="scan", text=None, filepath=None, style="report", **params):
        try:
            if op == "styles":
                return ok({"styles": writing.list_styles()})
            if op == "scan":
                if not text:
                    return fail("scan 需 text（待检中文文本）")
                report = writing.scan(text, filepath=filepath)
                return ok({"report": report, "passed": report.get("passed"),
                           "fail_count": report.get("fail_count"),
                           "layers": report.get("layers")})
            if op == "ai_taste":
                if not text:
                    return fail("ai_taste 需 text")
                rpt = writing.ai_taste(text, style=style)
                return ok({"report": rpt, "ai_score": rpt.get("ai_score"),
                           "hard_fails": rpt.get("hard_fails"),
                           "verdict": rpt.get("verdict")})
            return fail(f"未知 op: {op}")
        except Exception as e:  # noqa: BLE001
            return fail(f"write-qa 运行异常: {e}", degraded=True)


if __name__ == "__main__":
    a = WriteQaAtom(name="write-qa", agent="write")
    a.load()
    text = "这是一个测试通过赋能闭环实现降维打击，综上所述我们需要破局。"
    r = a.run(op="scan", text=text)
    assert r["ok"], "scan 空壳!"
    print("scan fail_count:", r["data"]["fail_count"], "passed:", r["data"]["passed"])
    r2 = a.run(op="ai_taste", text=text, style="report")
    assert r2["ok"], "ai_taste 空壳!"
    print("ai_score:", r2["data"]["ai_score"], "verdict:", r2["data"]["verdict"])
    r3 = a.run(op="styles")
    assert r3["ok"] and len(r3["data"]["styles"]) >= 4, "styles 空壳!"
    print("styles:", list(r3["data"]["styles"].keys()))
    print("write-qa 独立自测通过")
