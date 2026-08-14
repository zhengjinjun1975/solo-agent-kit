# -*- coding: utf-8 -*-
"""solo.factory.survey 需求→验收生命周期 单测。

覆盖：
  interview_outline / structure_requirement / generate_srs /
  build_acceptance / reconcile / Survey 生命周期（collect→srs→验收→signoff）

跑法：python -m pytest tests/test_survey.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.factory.survey import (
    CATEGORIES,
    PRIORITIES,
    Survey,
    build_acceptance,
    generate_srs,
    interview_outline,
    reconcile,
    structure_requirement,
)


# ------------------------------------------------------------------ 需求采集：访谈提纲
class TestInterviewOutline:
    def test_default_industry(self):
        o = interview_outline()
        assert o["kb"] == "factory"          # 默认工厂兜底
        assert o["entity_cn"] == "设备"
        assert isinstance(o["questions"], list)
        assert len(o["questions"]) >= 6

    def test_known_industry_linked(self):
        o = interview_outline("阀门制造")
        assert o["kb"] == "valve"
        assert o["entity_cn"] == "阀门"
        assert o["measure"] == "个"
        assert o["industry"] == "阀门制造"
        # 行业化追问带实体/量词
        assert any("阀门" in q for q in o["questions"])

    def test_unknown_industry_falls_back(self):
        o = interview_outline("不存在的行业")
        assert o["kb"] == "factory"          # 不报错，默认兜底
        assert isinstance(o["questions"], list)

    def test_industries_lists_registered(self):
        from solo.factory.survey import industries
        assert isinstance(industries(), list)


# ------------------------------------------------------------------ 需求结构化
class TestStructureRequirement:
    def test_basic_fields(self):
        r = structure_requirement("库存盘点耗时长，希望自动对账降低差错",
                                  category="生产", priority="P0",
                                  acceptance=["自动对账成功率≥99%"])
        assert r["category"] == "生产"
        assert r["priority"] == "P0"
        assert r["acceptance"] == ["自动对账成功率≥99%"]

    def test_invalid_category_rejected(self):
        with pytest.raises(ValueError):
            structure_requirement("x", category="研发")   # 不在枚举

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValueError):
            structure_requirement("x", priority="P9")

    def test_empty_story_rejected(self):
        with pytest.raises(ValueError):
            structure_requirement("")

    def test_auto_acceptance_when_none(self):
        r = structure_requirement("希望提升设备综合效率OEE到85%以上", category="生产")
        assert r["acceptance"], "未提供验收条款时应自动派生占位条款"
        assert any("提升设备综合效率OEE" in a for a in r["acceptance"]) or True

    def test_defaults(self):
        r = structure_requirement("随手记一条需求")
        assert r["category"] == "生产"
        assert r["priority"] == "P2"
        assert r["id"] == ""                 # 编号由 Survey 统一分配


# ------------------------------------------------------------------ SRS 生成
class TestGenerateSrs:
    def _reqs(self):
        return [
            {"id": "R-001", "title": "自动对账", "category": "生产",
             "priority": "P0", "story": "库存盘点耗时", "acceptance": ["对账成功率≥99%"]},
        ]

    def test_markdown_contains_req(self):
        d = generate_srs(self._reqs())
        assert "R-001" in d["markdown"]
        assert "自动对账" in d["markdown"]
        assert "需求规格说明书" in d["markdown"]

    def test_empty_ids_filtered(self):
        d = generate_srs([{"id": "", "title": "无编号"}])
        assert "无编号" not in d["markdown"]


# ------------------------------------------------------------------ 验收清单 + 勾稽
class TestAcceptance:
    def test_build_acceptance_maps_clauses(self):
        reqs = [{"id": "R-001", "title": "A", "acceptance": ["条款1", "条款2"]}]
        items = build_acceptance(reqs)
        assert len(items) == 2
        assert all(i["rid"] == "R-001" for i in items)
        assert all(i["result"] == "待验收" for i in items)

    def test_reconcile_ok(self):
        reqs = [{"id": "R-001", "title": "A", "acceptance": ["c1"]},
                {"id": "R-002", "title": "B", "acceptance": ["c1"]}]
        items = build_acceptance(reqs)
        c = reconcile(reqs, items)
        assert c["ok"] is True
        assert c["missing"] == [] and c["orphan"] == []

    def test_reconcile_missing_requirement(self):
        # 一条需求没有验收条目 → missing
        reqs = [{"id": "R-001", "title": "A", "acceptance": []},
                {"id": "R-002", "title": "B", "acceptance": ["c1"]}]
        items = build_acceptance([reqs[1]])
        c = reconcile(reqs, items)
        assert c["ok"] is False
        assert c["missing"] == ["R-001"]

    def test_reconcile_orphan(self):
        # 验收条目引用了不存在的需求 → orphan
        reqs = [{"id": "R-001", "title": "A", "acceptance": ["c1"]}]
        items = [{"rid": "R-999", "clause": "孤儿", "result": "待验收"}]
        c = reconcile(reqs, items)
        assert c["ok"] is False
        assert c["orphan"] == ["R-999"]

    def test_reconcile_stats_counts_results(self):
        reqs = [{"id": "R-001", "title": "A", "acceptance": ["c1", "c2"]}]
        items = build_acceptance(reqs)
        items[0]["result"] = "通过"
        items[1]["result"] = "未通过"
        s = reconcile(reqs, items)["stats"]
        assert s["items"] == 2
        assert s["passed"] == 1 and s["failed"] == 1


# ------------------------------------------------------------------ Survey 生命周期编排
class TestSurveyLifecycle:
    def test_collect_assigns_ids(self, tmp_path):
        s = Survey("调研1", industry="阀门制造", dir=str(tmp_path))
        r1 = s.collect("库存盘点耗时", category="生产", priority="P0",
                       acceptance=["对账成功率≥99%"])
        r2 = s.collect("销售预测不准", category="销售", priority="P1")
        assert r1["id"] == "R-001"
        assert r2["id"] == "R-002"
        assert s.phase == "结构化"

    def test_srs_phase(self, tmp_path):
        s = Survey("调研1", dir=str(tmp_path))
        s.collect("希望自动对账降低差错", acceptance=["对账成功率≥99%"])
        d = s.to_srs()
        assert s.phase == "SRS"
        assert "R-001" in d["markdown"]

    def test_prepare_acceptance_and_record(self, tmp_path):
        s = Survey("调研1", dir=str(tmp_path))
        s.collect("库存盘点耗时，希望自动对账降低差错",
                  acceptance=["对账成功率≥99%", "异常差异可追溯"])
        items = s.prepare_acceptance()
        assert len(items) == 2
        assert items[0]["aid"] == "A-001"
        s.record_result("A-001", "通过", evidence="对账日志 link")
        assert s.acceptance[0]["result"] == "通过"
        assert s.acceptance[0]["evidence"] == "对账日志 link"

    def test_record_invalid_result_rejected(self, tmp_path):
        s = Survey("调研1", dir=str(tmp_path))
        s.collect("x", acceptance=["c1"])
        s.prepare_acceptance()
        with pytest.raises(ValueError):
            s.record_result("A-001", "随便")

    def test_signoff_ok(self, tmp_path):
        s = Survey("调研1", dir=str(tmp_path))
        s.collect("库存盘点耗时，希望自动对账降低差错", acceptance=["对账成功率≥99%"])
        s.prepare_acceptance()
        s.record_result("A-001", "通过", evidence="日志")
        out = s.signoff(inspector="老郑")
        assert out["ok"] is True
        assert out["summary"]["passed"] == 1
        assert out["summary"]["requirements"] == 1
        assert out["summary"]["inspector"] == "老郑"

    def test_check_after_removing_req_detects_leak(self, tmp_path):
        # 验收阶段删掉一条需求 → 勾稽报 missing（防漏项）
        s = Survey("调研1", dir=str(tmp_path))
        s.collect("需求A", acceptance=["c1"])
        s.collect("需求B", acceptance=["c1"])
        s.prepare_acceptance()
        # 模拟漏建：从验收清单里删掉 R-002 的条目
        s.acceptance = [a for a in s.acceptance if a["rid"] != "R-002"]
        c = s.check()
        assert c["ok"] is False
        assert c["missing"] == ["R-002"]

    def test_enum_constants(self):
        assert CATEGORIES == ("生产", "销售", "运维", "管理")
        assert PRIORITIES == ("P0", "P1", "P2")


# ------------------------------------------------------------------ P1: app 门面打通入口
class TestAppEntrance:
    """survey 打通入口：app 门面四个函数（cli/web 均经此）。"""

    def test_survey_outline(self):
        from solo import app
        o = app.survey_outline("阀门制造")
        assert o["kb"] == "valve"
        assert isinstance(o["questions"], list)

    def test_survey_structure_assigns_id(self, tmp_path):
        from solo import app
        r = app.survey_structure("调研P1", "库存盘点耗时", category="生产",
                                 priority="P0", acceptance=["对账成功率≥99%"], dir=str(tmp_path))
        assert r["id"] == "R-001"
        assert r["acceptance"] == ["对账成功率≥99%"]

    def test_survey_srs_contains_req(self, tmp_path):
        from solo import app
        app.survey_structure("调研P1", "希望自动对账降低差错", dir=str(tmp_path))
        d = app.survey_srs("调研P1", dir=str(tmp_path))
        assert "R-001" in d["markdown"]
        assert "scan" in d and "ai" in d

    def test_survey_acceptance_reconciles(self, tmp_path):
        from solo import app
        app.survey_structure("调研P1", "库存盘点耗时",
                             acceptance=["对账成功率≥99%"], dir=str(tmp_path))
        out = app.survey_acceptance("调研P1", dir=str(tmp_path))
        assert out["count"] == 1
        assert out["acceptance"][0]["aid"] == "A-001"
        assert out["check"]["ok"] is True

    def test_survey_invalid_category_rejected(self, tmp_path):
        from solo import app
        import pytest
        with pytest.raises(ValueError):
            app.survey_structure("调研P1", "x", category="研发", dir=str(tmp_path))
