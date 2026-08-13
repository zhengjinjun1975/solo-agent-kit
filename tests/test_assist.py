# -*- coding: utf-8 -*-
"""solo×factory 集成函数单测（P1-2）。

覆盖 FDE 交付辅助 5 个契约核心函数：
  draft_questions / lexicon_draft / to_factory_lexicon /
  to_review_items / report_draft_dict

跑法：python -m pytest tests/test_assist.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.factory.assist import (
    draft_questions,
    lexicon_draft,
    to_factory_lexicon,
    to_review_items,
    report_draft_dict,
)

# 三行设备数据: 含 id 列(应被过滤)、文本列、数值列、枚举列
ROWS = [
    {"id": "1", "device_name": "车床A", "device_type": "车床", "power_kw": "50", "status": "运行", "zone": "一车间"},
    {"id": "2", "device_name": "铣床B", "device_type": "铣床", "power_kw": "80", "status": "待机", "zone": "一车间"},
    {"id": "3", "device_name": "车床C", "device_type": "车床", "power_kw": "60", "status": "运行", "zone": "二车间"},
]
HEADERS = ["id", "device_name", "device_type", "power_kw", "status", "zone"]


# ------------------------------------------------------------------ draft_questions
class TestDraftQuestions:
    def test_empty_rows(self):
        assert draft_questions([]) == []

    def test_basic_count_and_no_id(self):
        qs = draft_questions(ROWS, entity_name="设备")
        assert qs
        assert qs[0] == "有多少台设备"
        # id/编号列不得生成问题
        assert not any("id" in q or "编号" in q for q in qs)

    def test_numeric_extreme_and_enum(self):
        qs = draft_questions(ROWS, entity_name="设备")
        joined = "|".join(qs)
        assert "功率最大的设备" in qs       # 数值列极值
        assert "设备类型有哪些" in qs       # 枚举列
        assert "状态有哪些" in qs           # status 枚举
        assert "区域有哪些" in qs           # zone 枚举

    def test_limit(self):
        qs = draft_questions(ROWS, entity_name="设备", limit=2)
        assert len(qs) <= 2
        assert qs[0] == "有多少台设备"

    def test_entity_measure(self):
        qs = draft_questions(ROWS, entity_name="产品")
        assert qs[0] == "有多少个产品"


# ------------------------------------------------------------------ lexicon_draft
class TestLexiconDraft:
    def test_types_and_enum(self):
        d = lexicon_draft(HEADERS, ROWS)
        assert set(d.keys()) == set(HEADERS)
        assert d["power_kw"]["type"] in ("integer", "decimal")
        assert d["device_type"]["type"] == "string"
        # 有限枚举列给出 enum
        assert sorted(d["device_type"]["enum"]) == sorted(["车床", "铣床"])

    def test_cn_suggest(self):
        d = lexicon_draft(HEADERS, ROWS)
        assert d["device_name"]["cn"] == "设备名称"
        assert "attr_cn2en" in d["power_kw"]["suggest"]  # 数值列建议补映射


# ------------------------------------------------------------------ to_factory_lexicon
class TestToFactoryLexicon:
    def test_contract_shape(self):
        d = lexicon_draft(HEADERS, ROWS)
        fx = to_factory_lexicon(d, table_name="设备", entity_cn="设备")
        for key in ("description", "attr_cn2en", "attr_en2cn", "type_cn2en",
                    "status_cn2en", "zone_cn2en", "entity_cn2en",
                    "numeric_fields", "field_aliases", "value_fields"):
            assert key in fx

    def test_id_filtered(self):
        d = lexicon_draft(HEADERS, ROWS)
        fx = to_factory_lexicon(d, table_name="设备", entity_cn="设备")
        # id 列不得进任何映射/别名/枚举
        assert "id" not in fx["attr_cn2en"]
        assert "id" not in fx["field_aliases"]
        assert "id" not in fx["value_fields"]

    def test_numeric_and_enum_mapped(self):
        d = lexicon_draft(HEADERS, ROWS)
        fx = to_factory_lexicon(d, table_name="设备", entity_cn="设备")
        assert fx["attr_cn2en"]["功率"] == "power_kw"
        assert fx["type_cn2en"]["车床"] == "车床"
        assert fx["status_cn2en"]["运行"] == "运行"
        assert fx["zone_cn2en"]["一车间"] == "一车间"
        assert fx["entity_cn2en"]["设备"] == "设备"


# ------------------------------------------------------------------ to_review_items (P2: 无 id 污染)
class TestToReviewItems:
    def test_no_id_pollution(self):
        d = lexicon_draft(HEADERS, ROWS)
        items = to_review_items(d)
        # 绝不出现 attr_mapping/id 或枚举到 id
        assert ("attr_mapping", "id", "id") not in items
        assert not any(i[1] == "id" for i in items)
        assert not any("id" == str(i[1]).lower() for i in items)

    def test_attr_and_enum_items(self):
        d = lexicon_draft(HEADERS, ROWS)
        items = to_review_items(d)
        keys = [it[1] for it in items]
        assert "功率" in keys                 # 数值列 → attr_mapping
        assert "车床" in keys and "铣床" in keys   # 枚举值 → type_enum
        assert ("attr_mapping", "功率", "power_kw") in items


# ------------------------------------------------------------------ report_draft_dict
class TestReportDraftDict:
    def test_fields_and_hit(self):
        r = report_draft_dict(kb="valve", industry="阀门制造", hit=0.75,
                              questions_n=20, hits=15, asset_versions=3,
                              health={"hypotheses": 5, "accepted": 3, "rolled_back": 1},
                              baseline=0.5, note="验收要点")
        assert r["kb"] == "valve"
        assert r["industry"] == "阀门制造"
        assert r["solo_draft"] is True
        assert r["命中率"]["current"] == 0.75
        assert r["命中率"]["baseline"] == 0.5
        assert round(r["命中率"]["提升"], 4) == 0.25
        assert r["资产版本数"] == 3
        assert r["自进化健康度"]["hypotheses"] == 5
        assert r["自进化健康度"]["accepted"] == 3
        assert r["自进化健康度"]["rolled_back"] == 1

    def test_defaults(self):
        r = report_draft_dict(kb="food", industry="食品制造", hit=0.0,
                              questions_n=0, hits=0)
        assert r["命中率"]["baseline"] is None
        assert r["命中率"]["提升"] is None
        assert r["资产版本数"] == 0
        assert r["自进化健康度"]["hypotheses"] == 0
