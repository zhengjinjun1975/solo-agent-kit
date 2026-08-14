# -*- coding: utf-8 -*-
"""factory.data 数据审视套件（clean + stats + audit 合并）单测。

覆盖：
  - 合并后的统一 API（DataCleaner / guess_type / describe / detect_anomaly / control_chart）
  - audit 四件套：schema(盘点) / dictionary(字典) / quality(质量) / report(一键报告)
  - 共享数值原语一次实现（clean/stats/audit 共用 is_num/quantile/guess_type）

跑法：python -m pytest tests/test_data_audit.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.factory import data


def _rows():
    return [
        {"id": "1", "temp_c": "45.2", "status": "运行"},
        {"id": "1", "temp_c": "45.2", "status": "运行"},   # 重复
        {"id": "2", "temp_c": "", "status": "运行"},        # 缺失
        {"id": "3", "temp_c": "45.3", "status": "运行"},
        {"id": "4", "temp_c": "45.4", "status": "运行"},
        {"id": "5", "temp_c": "45.1", "status": "运行"},
        {"id": "6", "temp_c": "80.0", "status": "运行"},    # 异常值
        {"id": "7", "temp_c": "45.5x", "status": "运行"},   # 类型漂移（非数值混入）
    ]


# ---- clean + stats 统一 API（原 clean.py/stats.py 行为等价）----
def test_cleaner_merged_api():
    """DataCleaner + describe/detect_anomaly/control_chart 在一个模块共存。"""
    cl = data.DataCleaner()
    out = cl.clean(_rows(), numeric_cols=["temp_c"], fill_missing="drop", outlier_method="iqr")
    assert cl.report["dropped_dup"] == 1
    assert cl.report["dropped_outlier"] == 1
    assert len(out) < len(_rows())
    desc = data.describe([45.2, 45.5, 45.1])
    assert desc["count"] == 3 and "mean" in desc
    assert data.guess_type("45.2") == "float"
    assert data.guess_type("") == "missing"


def test_clean_stats_share_guessing():
    """guess_type 单一实现，供 clean 报告与 audit 复用。"""
    assert data.guess_type("2024-01-01") == "date"
    assert data.guess_type("abc") == "text"
    assert data.guess_type("12") == "integer"


# ---- audit.schema 盘点 ----
def test_schema_pan():
    s = data.schema(_rows())
    assert s["total_rows"] == 8
    assert set(s["columns"]) == {"id", "temp_c", "status"}
    f = s["fields"]["temp_c"]
    assert f["type"] == "float"
    assert f["non_empty"] == 7          # 8 行 - 1 缺失
    assert f["missing"] == 1
    assert f["unique"] == 7


# ---- audit.dictionary 字典 ----
def test_dictionary_cn_measure_enum():
    d = data.dictionary(_rows())
    assert d["total_rows"] == 8
    tf = d["fields"]["temp_c"]
    assert "温度" in tf["cn"]           # 列名 → 中文猜测
    assert "℃" in tf["measure"]        # 计量单位猜测
    st = d["fields"]["status"]
    assert st["enum"] == ["运行"]       # 低基数 → 枚举值
    assert "caliber" in tf


# ---- audit.quality 质量 ----
def test_quality_flags_missing_dup_outlier_drift():
    q = data.quality(_rows())
    assert q["ok"] is False
    types = {i["type"] for i in q["issues"]}
    assert "missing" in types
    assert "duplicate" in types
    assert "outlier" in types
    assert "type_drift" in types
    assert q["metrics"]["duplicates"] == 1
    assert q["missing"]["temp_c"] == 1
    assert any(i.get("column") == "temp_c" and i["type"] == "type_drift" for i in q["issues"])


def test_quality_clean_rows_ok():
    clean = [{"id": "1", "temp_c": "45.2", "status": "运行"},
             {"id": "2", "temp_c": "45.3", "status": "运行"}]
    q = data.quality(clean)
    assert q["ok"] is True


# ---- audit.report 一键报告 ----
def test_report_aggregates_all():
    r = data.report(_rows())
    assert set(r.keys()) == {"schema", "dictionary", "quality", "stats", "preview"}
    assert r["schema"]["total_rows"] == 8
    assert "temp_c" in r["stats"]       # 数值列描述统计
    assert len(r["preview"]) == 5
