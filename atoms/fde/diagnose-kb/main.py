# -*- coding: utf-8 -*-
"""diagnose-kb 原子：FDE 诊断深度——故障知识库「积累 → 诊断 → 根因分析」闭环。

把 monitor 告警 + 人工/经验结论沉淀为运维故障知识库（问题→根因→解决方案），
新症状通过大词共现检索命中最相关案例，输出**根因分析**（cause）与**解决方案**，
并给出置信度。纯标准库、离线可算、数据本地自持（data/diagnose/*.json）。

闭环：
  learn(symptom, cause, solution, signals, device)   → 沉淀一条知识（积累）
  diagnose(symptom, signals, device)                 → 匹配历史 → 根因 + 方案 + 置信度
  list()                                             → 列出故障库
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
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402


def _tok(text: str) -> list:
    text = (text or "").lower()
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    tokens = []
    for seg in cjk:
        seg = seg.strip()
        for i in range(len(seg) - 1):
            tokens.append(seg[i:i + 2])
        if len(seg) == 1:
            tokens.append(seg)
    tokens += re.findall(r"[a-z][a-z0-9_]{1,}", text)
    return tokens


class FaultKnowledge:
    """故障知识库（纯标准库，持久化到 data/diagnose/<kb>.json）。"""

    def __init__(self, kb_dir: str):
        self.kb_dir = kb_dir
        os.makedirs(kb_dir, exist_ok=True)

    def _path(self, kb: str):
        name = re.sub(r"[^0-9a-zA-Z_-]", "_", kb or "faults") or "faults"
        return os.path.join(self.kb_dir, name + ".json")

    def _load(self, kb: str) -> list:
        p = self._path(kb)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                    return d if isinstance(d, list) else []
            except Exception:
                return []
        return []

    def _save(self, kb: str, entries: list) -> None:
        with open(self._path(kb), "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def learn(self, kb: str, entry: dict) -> dict:
        entries = self._load(kb)
        if entry.get("symptom") not in [e.get("symptom") for e in entries]:
            entries.append(entry)
        self._save(kb, entries)
        return {"entry": entry, "total": len(entries)}

    def match(self, kb: str, symptom: str, signals=None, device=None, top=3) -> list:
        entries = self._load(kb)
        q = set(_tok(symptom or ""))
        for k, v in (signals or {}).items():
            q |= set(_tok(f"{k} {v}"))
        if device:
            q |= set(_tok(device))
        scored = []
        for e in entries:
            pool = set(_tok(e.get("symptom") or ""))
            pool |= set(_tok((e.get("device") or "") + " " + str(e.get("signals") or "")))
            inter = len(q & pool)
            union = len(q | pool) or 1
            jac = inter / union
            # 信号匹配加成
            bonus = 0.0
            sig = e.get("signals") or {}
            if signals and isinstance(sig, dict):
                hit = sum(1 for k, v in sig.items()
                          if str(v).strip() and str(v) == str(signals.get(k, "")).strip())
                bonus = 0.15 * hit
            scored.append({"entry": e, "score": round(jac + bonus, 3)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        out = [{
            "symptom": s["entry"].get("symptom"),
            "cause": s["entry"].get("cause"),
            "solution": s["entry"].get("solution"),
            "device": s["entry"].get("device"),
            "confidence": s["score"],
        } for s in scored[:top] if s["score"] > 0]
        return out


class DiagnoseKbAtom(AtomicAgent):
    def capabilities(self):
        return ["diagnose.kb"]

    def _run(self, op: str = "list", dir: str = None, **params):
        kb_dir = dir or os.path.join(_ROOT, "data", "diagnose")
        kb = FaultKnowledge(kb_dir)
        kb_name = params.get("kb", "faults")
        if op == "learn":
            symptom, cause, solution = (params.get("symptom"), params.get("cause"),
                                        params.get("solution"))
            if not symptom or not cause:
                return fail("learn 需 symptom + cause (+solution)")
            r = kb.learn(kb_name, {
                "symptom": symptom, "cause": cause,
                "solution": solution or "（待补充处理方案）",
                "device": params.get("device"), "signals": params.get("signals") or {},
            })
            return ok(r)
        if op == "diagnose":
            symptom = params.get("symptom")
            if not symptom:
                return fail("diagnose 需 symptom")
            hits = kb.match(kb_name, symptom, signals=params.get("signals"),
                            device=params.get("device"))
            if not hits:
                return ok({"diagnosis": None, "hit": False,
                           "note": "故障库无匹配，建议先 learn 沉淀该问题"})
            return ok({"diagnosis": hits[0], "candidates": hits, "hit": True})
        if op == "list":
            return ok({"entries": kb._load(kb_name)})
        if op == "linkage":
            return ok({"boundary": "算法开源，故障数据本地自持（data/diagnose/），不出厂"})
        return fail(f"未知 op: {op}")


def _main():
    a = DiagnoseKbAtom(name="diagnose-kb", agent="fde", version="0.1.0")
    a.load()
    import tempfile
    d = tempfile.mkdtemp(prefix="fde_diag_")
    # 沉淀两条故障知识
    a.run(op="learn", dir=d, symptom="水泵振动超限", cause="轴承磨损",
          solution="更换轴承并做动平衡，振动恢复5.0以内", device="pump_01",
          signals={"vibration": 8.6})
    a.run(op="learn", dir=d, symptom="电机温度偏高", cause="散热不良/轴承润滑不足",
          solution="清理散热片并补充润滑脂", device="motor_02",
          signals={"temp": 95})
    # 新症状命中历史 → 根因 + 方案 + 置信度
    r = a.run(op="diagnose", dir=d, symptom="水泵振动大",
              signals={"vibration": 8.6}, device="pump_01")
    assert r.get("ok") and r["data"]["hit"], "诊断应命中故障库"
    print("  diagnose cause:", r["data"]["diagnosis"]["cause"],
          "conf:", r["data"]["diagnosis"]["confidence"])
    # 未知症状应诚实 miss
    r2 = a.run(op="diagnose", dir=d, symptom="完全没见过的新故障现象XYZ")
    assert r2.get("ok") and not r2["data"]["hit"], "未知症状应 miss(防幻觉)"
    print("  unknown miss:", r2["data"]["note"])
    print("diagnose-kb 独立自测通过, 0 失败")


if __name__ == "__main__":
    _main()
