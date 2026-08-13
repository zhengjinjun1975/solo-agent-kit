# -*- coding: utf-8 -*-
"""zh_ai_taste.py — zh-writing-checker 生态接入适配器（生成→AI味检测→提示/建议闭环）。

零依赖（仅标准库）。运行时动态定位并加载 zh-writing-checker 单文件模块，
找不到则降级为"未接入"提示，不阻断业务。提供两个入口：
  - ai_taste_report(text, style) -> dict  结构化结果（AI味评分 + 建议）
  - format_ai_report(report, source=) -> str  人类可读提示（打印/日志用）

评分逻辑（对齐 zh-writing-checker 两层四维）：
  - 人味门检 human_gate：真人文本直接高分（不误伤声口）
  - AI味分 = 100 - D5(去AI味) 权值 - D6(活人感) 惩罚
  - 语言层 L1(D1-D4) fail 项计入硬伤分，提示必改
评分仅供参考，只提示不强制改写。
"""
from __future__ import annotations

import importlib.util
import os
import sys

# ── 定位 zh-writing-checker 单文件模块 ─────────────────────────────
# 候选路径：环境变量 → 常见源码根。任一命中即可，找不到不报错。
_CANDIDATES = [
    os.environ.get("ZH_WRITING_CHECKER", ""),
    r"E:/open-source/zh-writing-checker/zh_writing_checker.py",
    r"C:/Users/ASUS Air/open-source/zh-writing-checker/zh_writing_checker.py",
]
# 相对回退：从本文件往上找 open-source 根（保证闭源工具在 E: 根即可命中）
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(4):
    _p = os.path.join(os.path.dirname(_here), *([".."] * _up),
                      "open-source", "zh-writing-checker", "zh_writing_checker.py")
    _CANDIDATES.append(os.path.normpath(_p))
_CANDIDATES = [p for p in _CANDIDATES if p]

_LOADED = None  # 模块对象 or None（未加载）


def _locate() -> str:
    for p in _CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return ""


def _load():
    """动态加载 zh-writing-checker 模块（单文件，无第三方依赖）。找不到返回 None。"""
    global _LOADED
    if _LOADED is not None:
        return _LOADED
    path = _locate()
    if not path:
        _LOADED = False
        return None
    try:
        spec = importlib.util.spec_from_file_location("_zh_writing_checker_rt", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LOADED = mod
    except Exception:
        _LOADED = False
        return None
    return _LOADED


def _penalty(sev, count):
    """各层级问题的AI味惩罚权重（主观项轻罚，客观错字/语病重罚提示必改）。"""
    w = {"fail": 3.0, "warn": 1.5, "info": 0.5}.get(sev, 1.0)
    return w * max(1, int(count or 1))


def ai_taste_report(text: str, style: str = "report") -> dict:
    """对一段文本做 AI 味检测 + 建议，返回结构化 dict。

    text: 待检中文文本。style: report/wechat/tweet/paper（仅用于提示措辞）。
    返回字段：
      ok / available  是否成功接入 zh-writing-checker
      human           人味门检结果（真人文本 True）
      register        语体识别
      ai_score        100为最像人，越低越AI腔
      hard_fails      语言层(L1)必改项数（错字/标点/语病/数字）
      soft_warns      D5/D6 建议项数
      issues          命中问题（含建议）
      suggestions     可执行改写建议列表
    """
    mod = _load()
    base = {
        "ok": False, "available": False, "human": None, "register": None,
        "ai_score": None, "hard_fails": 0, "soft_warns": 0,
        "issues": [], "suggestions": [], "note": "zh-writing-checker 未接入（未定位到模块）",
    }
    if mod is None:
        return base

    try:
        gate = mod.human_gate(text)
        register = mod.register_of(text)
        scan = mod.scan_text(text)
    except Exception as e:  # noqa: BLE001
        base["note"] = f"检测异常: {e}"
        return base

    # 汇总问题
    issues = list(scan.get("issues", []))
    hard_fails = sum(1 for i in issues if i.get("layer") in ("D1", "D2", "D3", "D4")
                     and i.get("severity") == "fail")
    soft_warns = sum(1 for i in issues if i.get("layer") in ("D5", "D6"))

    # AI味分：门检真人→高分；否则按 D5/D6 惩罚
    ai_score = 100.0
    if gate and gate.get("human"):
        ai_score = 95.0
    else:
        for i in issues:
            if i.get("layer") in ("D5", "D6"):
                ai_score -= _penalty(i.get("severity", "warn"), i.get("count", 1))
    ai_score = max(0.0, min(100.0, round(ai_score, 1)))

    # 改写建议（只提示不强制）
    suggestions = []
    for i in issues:
        sug = i.get("suggestion") or ""
        if sug:
            suggestions.append(f"[{i.get('layer')}] {i.get('type')}: {sug}")

    result = {
        "ok": True, "available": True,
        "human": bool(gate and gate.get("human")),
        "register": register,
        "ai_score": ai_score,
        "hard_fails": hard_fails, "soft_warns": soft_warns,
        "issues": issues, "suggestions": suggestions,
        "note": f"AI味分 {ai_score}（100=最像人）",
    }
    if gate and gate.get("human"):
        result["note"] = "命中真人文本，停手不改声口。" + result["note"]
    return result


def format_ai_report(report: dict, source: str = "文本") -> str:
    """把 ai_taste_report 渲染为人类可读的提示（打印/日志用）。"""
    if not report.get("ok"):
        return f"[AI味自检] {source}: {report.get('note', '未接入')}"
    lines = []
    level = ("自然" if report["ai_score"] >= 80 else
             "略AI腔" if report["ai_score"] >= 60 else "AI腔明显")
    lines.append(f"[AI味自检] {source}: 分 {report['ai_score']}（{level}）"
                 f" | L1必改 {report['hard_fails']} 项 | D5/D6建议 {report['soft_warns']} 项")
    if report["register"]:
        lines.append(f"  语体识别: {report['register']}")
    if report["human"]:
        lines.append("  人味门检: 命中真人文本，停手不改声口。")
    sugs = report["suggestions"]
    if sugs:
        lines.append("  建议（不强制，按需取舍）:")
        for s in sugs[:8]:
            lines.append(f"    - {s}")
    else:
        lines.append("  未发现需改写项。")
    return "\n".join(lines)
