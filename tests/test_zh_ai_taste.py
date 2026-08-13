# -*- coding: utf-8 -*-
"""test_zh_ai_taste.py — AI味自检闭环（接入 zh-writing-checker）测试。

验证: ai_taste 返回评分/建议; format_ai_taste 渲染; write_natural 闭环给出
前后 AI 味分对比; 未接入检查器时优雅降级。
"""
import pytest

from solo import writing as w


def test_ai_taste_detects_ai_words():
    ai_text = "在当今时代，随着科技的进步，我们赋能传统流程，实现价值沉淀，综上所述形成闭环。"
    rep = w.ai_taste(ai_text)
    # 检查器可接入（环境内有 zh-writing-checker）则给出 D5 建议
    if rep.get("ok"):
        assert rep["ai_score"] is not None
        assert 0 <= rep["ai_score"] <= 100
        types = {i["type"] for i in rep["issues"]}
        assert any("禁用词" in t or "教科书" in t or "破折号" in t for t in types)


def test_format_ai_taste_render():
    rep = w.ai_taste("这是一句普通中文。")
    text = w.format_ai_taste(rep, source="测试")
    if rep.get("ok"):
        assert "[AI味自检]" in text


def test_write_natural_closed_loop():
    ai_text = "在当今时代，随着科技的进步，我们赋能传统流程，实现价值沉淀。"
    out = w.write_natural(ai_text, style="report", provider=None)
    assert "ai_taste_before" in out
    assert "rewrite" in out


def test_ai_taste_degrades_gracefully(monkeypatch):
    # 模拟找不到检查器：改候选路径为空 → ok=False 不抛异常
    import solo.zh_ai_taste as zat
    monkeypatch.setattr(zat, "_CANDIDATES", [])
    monkeypatch.setattr(zat, "_LOADED", None)
    rep = zat.ai_taste_report("任意文本")
    assert rep["ok"] is False
    assert rep["ai_score"] is None
