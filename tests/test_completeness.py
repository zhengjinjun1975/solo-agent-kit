# -*- coding: utf-8 -*-
"""solo(FDE工具箱) 功能补全回归（2026-08 系统补全）。

覆盖 P1 4 项 + P2 5 项：
  P1-1 survey 行业追问不逐字拆
  P1-2 _detect_numeric_col 跳 id 主键列
  P1-3 to_factory_lexicon 删恒真 or True + 滤名称类列 + 英文建议非恒等
  P1-4 Ontology.answer 聚合问答（计数/极值/枚举/列表）闭环
  P2-5 CLI 入口补齐（code-review/writing/memory/optmem/onto/to-factory-lexicon/to-review-items）
  P2-6 industry-set 接线 review 队列
  P2-7 lexicon_draft 跳过 id 列（标记 identifier）
  P2-8 report/ai_taste 评分自洽（verdict 不矛盾）
  P2-9 中文列英文建议字段（非恒等映射）

跑法：python -m pytest tests/test_completeness.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROWS = [
    {"id": "1", "device_name": "车床A", "device_type": "车床", "power_kw": "50", "status": "运行", "zone": "一车间"},
    {"id": "2", "device_name": "铣床B", "device_type": "铣床", "power_kw": "80", "status": "待机", "zone": "一车间"},
    {"id": "3", "device_name": "车床C", "device_type": "车床", "power_kw": "60", "status": "运行", "zone": "二车间"},
]
HEADERS = list(ROWS[0].keys())


# ══════════════════════════════════════════════════════════════════════
# P1-1 survey 行业追问不逐字拆
# ══════════════════════════════════════════════════════════════════════
class TestSurveyNoCharSplit:
    def test_valve_note_not_char_split(self):
        from solo.factory.survey import interview_outline
        o = interview_outline("阀门制造")
        q = next(q for q in o["questions"] if q.startswith("行业"))
        # 追问应整句带出 note（"公称通径" 若被 '、'.join 逐字拆会变成"公、称、通、径"）
        assert "关注公称通径" in q
        assert "公、称" not in q

    def test_unknown_industry_uses_行业要点(self):
        from solo.factory.survey import interview_outline
        o = interview_outline("不存在行业")
        q = next(q for q in o["questions"] if q.startswith("行业"))
        assert "针对行业要点" in q  # note 为空 → 兜底"行业要点"，不是逐字拆


# ══════════════════════════════════════════════════════════════════════
# P1-2 _detect_numeric_col 跳 id 主键列
# ══════════════════════════════════════════════════════════════════════
class TestDetectNumericColSkipId:
    def test_skips_id(self):
        from solo.app import _detect_numeric_col
        # id 是首个数值列，但应跳过 → 命中 power_kw
        assert _detect_numeric_col(ROWS) == "power_kw"

    def test_fallback_to_id_if_only_id_numeric(self):
        from solo.app import _detect_numeric_col
        rows = [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]
        # 无非 id 数值列 → 回退允许 id（避免空白）
        assert _detect_numeric_col(rows) == "id"


# ══════════════════════════════════════════════════════════════════════
# P1-3 + P2-7 + P2-9 lexicon_draft / to_factory_lexicon
# ══════════════════════════════════════════════════════════════════════
class TestLexiconAndFactoryLexicon:
    def test_lexicon_draft_marks_id_identifier(self):
        from solo.factory.assist import lexicon_draft
        d = lexicon_draft(HEADERS, ROWS)
        assert d["id"]["type"] == "identifier"          # P2-7 跳过 id（不进属性/枚举）
        assert d["id"]["enum"] is None

    def test_no_identity_type_pollution(self):
        from solo.factory.assist import lexicon_draft, to_factory_lexicon
        d = lexicon_draft(HEADERS, ROWS)
        fx = to_factory_lexicon(d, table_name="设备", entity_cn="设备")
        # P1-3 删恒真 or True：device_name 是名称列，不得污染 type_cn2en
        assert "设备名称" not in fx["type_cn2en"]
        assert "车床" in fx["type_cn2en"]
        # 名称列仍作属性映射（不丢失）
        assert fx["attr_cn2en"].get("设备名称") == "device_name"

    def test_value_en_suggest_non_identity(self):
        from solo.factory.assist import lexicon_draft, to_factory_lexicon
        d = lexicon_draft(HEADERS, ROWS)
        fx = to_factory_lexicon(d, table_name="设备", entity_cn="设备")
        # P2-9 中文枚举值给英文建议（非恒等映射）
        assert "value_en_suggest" in fx
        assert fx["value_en_suggest"]["运行"]["en"] == "running"       # 已知词 → 英文
        assert fx["value_en_suggest"]["运行"]["needs_translation"] is False
        # type_cn2en/status_cn2en 仍是中文自身（契约向后兼容），英文建议在独立字段
        assert fx["status_cn2en"]["运行"] == "运行"
        assert fx["type_cn2en"]["车床"] == "车床"

    def test_unknown_chinese_value_flagged_translation(self):
        from solo.factory.assist import _en_suggest
        r = _en_suggest("自定义车间X")
        assert r["en"] == "" and r["needs_translation"] is True


# ══════════════════════════════════════════════════════════════════════
# P1-4 Ontology.answer 聚合问答闭环
# ══════════════════════════════════════════════════════════════════════
class TestOntologyAnswerAggregate:
    @pytest.fixture()
    def ont(self):
        from solo.factory.ontology import Ontology
        o = Ontology()
        o.from_rows(ROWS, entity_name="设备")
        o.build()
        return o

    def test_count(self, ont):
        assert ont.answer("有多少台设备") == [{"type": "count", "entity": "设备",
                                               "question": "有多少台设备", "value": 3}]

    def test_extreme_max_min(self, ont):
        a = ont.answer("功率最大的设备")
        assert a[0]["type"] == "extreme" and a[0]["extreme"] == "最大"
        assert float(a[0]["value"]) == 80.0
        b = ont.answer("功率最小的设备")
        assert b[0]["extreme"] == "最小" and float(b[0]["value"]) == 50.0

    def test_enum(self, ont):
        assert ont.answer("设备类型有哪些")[0]["values"] == ["车床", "铣床"]
        assert ont.answer("状态有哪些")[0]["values"] == ["待机", "运行"]
        assert ont.answer("区域有哪些")[0]["values"] == ["一车间", "二车间"]

    def test_list_names(self, ont):
        a = ont.answer("有哪些设备")
        assert a[0]["type"] == "list"
        assert set(a[0]["values"]) == {"车床A", "车床C", "铣床B"}


# ══════════════════════════════════════════════════════════════════════
# P2-6 industry-set 接线 review 队列
# ══════════════════════════════════════════════════════════════════════
class TestIndustryReviewWiring:
    def test_rebuild_includes_review_items(self, tmp_path, monkeypatch):
        from solo.factory import industry as ind_mod
        monkeypatch.setattr(ind_mod, "_STATE_FILE", str(tmp_path / "cur.json"))
        bundle = ind_mod.rebuild_industry_artifacts("阀门制造", rows=ROWS, out_dir=None)
        assert "review_items" in bundle["artifacts"]
        assert bundle["artifacts"]["review_items"]  # 非空
        # 含属性/枚举待确认项，且无 id 污染
        keys = [it[1] for it in bundle["artifacts"]["review_items"]]
        assert "功率" in keys
        assert not any(str(k).lower() == "id" for k in keys)


# ══════════════════════════════════════════════════════════════════════
# P2-8 ai_taste / report 评分自洽
# ══════════════════════════════════════════════════════════════════════
class TestAiTasteSelfConsistent:
    def test_verdict_self_consistent(self):
        from solo import writing as w
        rep = w.ai_taste("今天天气不错，我们决定调整生产计划", style="report")
        if not rep.get("ok"):
            pytest.skip("zh-writing-checker 未接入")
        # verdict 必须存在且与 score/fail 不矛盾
        assert "verdict" in rep
        if rep["hard_fails"] > 0:
            assert "修正" in rep["verdict"] or "必改" in rep["verdict"]
        else:
            assert rep["verdict"]  # 非空


# ══════════════════════════════════════════════════════════════════════
# P2-5 CLI 入口补齐（注册 + 核心命令可跑）
# ══════════════════════════════════════════════════════════════════════
class TestCliEntries:
    def test_all_commands_registered(self):
        import argparse
        from solo.cli import main
        # 通过参数解析验证子命令已注册（不实际执行）
        parser = argparse.ArgumentParser(prog="solo")
        sub = parser.add_subparsers(dest="cmd")
        # 轻量校验：读取 cli 模块内的注册逻辑由 main() 触发
        # 直接调用 main 的解析层会打印，故用 import 侧检查
        import solo.cli as cli_mod
        src = open(cli_mod.__file__, encoding="utf-8").read()
        for name in ("code-review", "writing-ai-taste", "writing-write-natural",
                     "memory-note", "memory-search", "optmem-note", "optmem-search",
                     "onto-to-nt", "onto-answer", "onto-search",
                     "to-factory-lexicon", "to-review-items"):
            assert f'"{name}"' in src or f"'{name}'" in src, f"CLI 未注册: {name}"

    def test_onto_answer_cli(self, tmp_path):
        import csv
        from solo.cli import main
        from solo import provider as provider_mod
        csv_path = tmp_path / "dev.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS)
            w.writeheader()
            w.writerows(ROWS)
        rc = main(["onto-answer", str(csv_path), "--entity", "设备", "有多少台设备"])
        assert rc == provider_mod.EXIT_OK

    def test_to_review_items_cli(self, tmp_path):
        import csv
        from solo.cli import main
        from solo import provider as provider_mod
        csv_path = tmp_path / "dev.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=HEADERS)
            w.writeheader()
            w.writerows(ROWS)
        rc = main(["to-review-items", str(csv_path)])
        assert rc == provider_mod.EXIT_OK
