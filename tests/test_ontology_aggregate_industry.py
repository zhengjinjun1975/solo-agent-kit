# -*- coding: utf-8 -*-
"""回归: 本体聚合问答行业化列名闭环（draft_questions 生成题 → onto-answer 可答）。

P2 断链修复回归：Ontology 注入行业 col_cn 后，行业化列名（阀门类型/公称通径/公称压力/材质）
生成的聚合题必须可答，与 draft_questions 行业措辞闭环。
"""
import csv
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALVE = os.path.join(REPO, "examples", "valve_demo_full.csv")

from solo.factory.ontology import Ontology  # noqa: E402

VALVE_COL_CN = {"valve_type": "阀门类型", "nominal_dn": "公称通径",
                "pressure_rating": "公称压力", "material": "材质"}


def _build(industry_col_cn=None):
    rows = list(csv.DictReader(open(VALVE, encoding="utf-8-sig")))
    o = Ontology(col_cn=industry_col_cn or {})
    o.from_rows(rows, entity_name="阀门", id_col="id")
    o.build()
    return o, rows


@pytest.fixture(scope="module")
def valve_rows():
    return list(csv.DictReader(open(VALVE, encoding="utf-8-sig")))


def test_aggregate_count(valve_rows):
    o = Ontology(); o.from_rows(valve_rows, entity_name="阀门", id_col="id"); o.build()
    a = o.answer("有多少台阀门")
    assert a and a[0]["type"] == "count" and a[0]["value"] == 10


def test_aggregate_global_extreme(valve_rows):
    o = Ontology(); o.from_rows(valve_rows, entity_name="阀门", id_col="id"); o.build()
    a = o.answer("功率最大的阀门")
    assert a and a[0]["type"] == "extreme" and a[0]["value"] == "9.0"


def test_aggregate_global_enum(valve_rows):
    o = Ontology(); o.from_rows(valve_rows, entity_name="阀门", id_col="id"); o.build()
    a = o.answer("状态有哪些")
    assert a and a[0]["type"] == "enum" and set(a[0]["values"]) >= {"在用", "故障"}


def test_aggregate_industry_enum(valve_rows):
    """行业化枚举（阀门类型）→ 注入 col_cn 后必答（原断链: 返回空）。"""
    o = Ontology(col_cn=VALVE_COL_CN)
    o.from_rows(valve_rows, entity_name="阀门", id_col="id"); o.build()
    a = o.answer("阀门类型有哪些")
    assert a and a[0]["type"] == "enum"
    assert "球阀" in a[0]["values"] and "闸阀" in a[0]["values"]


def test_aggregate_industry_extreme(valve_rows):
    """行业化极值（公称通径）→ 注入 col_cn 后必答。"""
    o = Ontology(col_cn=VALVE_COL_CN)
    o.from_rows(valve_rows, entity_name="阀门", id_col="id"); o.build()
    a = o.answer("公称通径最小的阀门")
    assert a and a[0]["type"] == "extreme" and a[0]["value"] == "25"


def test_aggregate_industry_material_enum(valve_rows):
    o = Ontology(col_cn=VALVE_COL_CN)
    o.from_rows(valve_rows, entity_name="阀门", id_col="id"); o.build()
    a = o.answer("材质有哪些")
    assert a and a[0]["type"] == "enum" and "不锈钢" in a[0]["values"]


def test_draft_questions_all_answerable():
    """draft_questions(阀门行业) 生成的每个题，注入行业 col_cn 后 onto-answer 必须可答。"""
    from solo.factory.assist import draft_questions
    from solo.factory.industry import load_industry
    from solo.factory.ontology import Ontology
    rows = list(csv.DictReader(open(VALVE, encoding="utf-8-sig")))
    ind_col_cn = dict(load_industry("阀门制造").get("col_cn") or {})
    qs = draft_questions(rows, "阀门", industry="阀门制造")
    o = Ontology(col_cn=ind_col_cn)
    o.from_rows(rows, entity_name="阀门", id_col="id"); o.build()
    unanswered = [q for q in qs if not o.answer(q, entity="阀门")]
    assert not unanswered, f"以下 draft_questions 生成题 onto-answer 答不出: {unanswered}"


def test_cli_onto_answer_industry():
    """CLI onto-answer --industry 真实可用（非仅定义）。"""
    import json
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "solo.cli", "onto-answer", VALVE,
                        "阀门类型有哪些", "--industry", "阀门制造"],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=REPO)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip())
    assert out.get("answers") and "球阀" in out["answers"][0]["values"]
