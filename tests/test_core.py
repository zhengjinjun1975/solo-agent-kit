# -*- coding: utf-8 -*-
"""solo-agent-kit 冒烟测试套件（pytest，零依赖测试）。

每个模块核心路径：本体/记忆/技能/写作/代码/任务/provider/cli。
跑法：python -m pytest tests/ -v
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import __version__
from solo import memory as memory_mod
from solo.factory import ontology as ontology_mod
from solo import skill as skill_mod
from solo import writing as writing_mod
from solo import code as code_mod
from solo import task as task_mod
from solo import provider as provider_mod


@pytest.fixture
def tmp():
    return tempfile.mkdtemp(prefix="solo-test-")


# ---- 版本 ----
def test_version():
    from solo import __version__
    # 版本是语义化的 X.Y.Z
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


# ---- memory：三层两域 ----
def test_memory_profile_override(tmp):
    m = memory_mod.Memory(mem_dir=os.path.join(tmp, "mem"))
    m.set_profile("role", "A")
    m.set_profile("role", "B")
    assert m.get_profile("role") == "B"


def test_memory_fact_dedup(tmp):
    m = memory_mod.Memory(mem_dir=os.path.join(tmp, "mem"))
    assert m.add_fact("事实X", ["t"]) is True
    assert m.add_fact("事实X", ["t"]) is False  # 去重


def test_memory_scenario_and_search(tmp):
    m = memory_mod.Memory(mem_dir=os.path.join(tmp, "mem"))
    m.set_scenario("proj", "企业决策平台,8决策")
    assert "8决策" in m.get_scenario("proj")
    m.add_fact("本体建模提升检索命中率", ["本体"])
    res = m.search("本体", top_k=2)
    assert res and "本体" in res[0]["text"]


def test_memory_obsidian_interop(tmp):
    m = memory_mod.Memory(mem_dir=os.path.join(tmp, "mem"))
    vault = os.path.join(tmp, "vault"); os.makedirs(vault)
    with open(os.path.join(vault, "n.md"), "w", encoding="utf-8") as f:
        f.write("一条可导入的记忆\n")
    added = m.import_markdown(vault)
    assert added >= 1
    out = os.path.join(tmp, "out")
    m.export_markdown(out)
    assert os.path.exists(os.path.join(out, "solo-memory.md"))


# ---- ontology：本体优先 ----
def test_ontology_csv(tmp):
    csvp = os.path.join(tmp, "dev.csv")
    with open(csvp, "w", encoding="utf-8") as f:
        f.write("id,name,status\n1,空压机,运行中\n2,泵,待维护\n")
    o = ontology_mod.Ontology()
    n = o.from_csv(csvp, entity_name="devices")   # 显式实体名
    assert n == 1 and "devices" in o.entities
    assert len(o.triples) == 6  # 2行×3列
    hits = o.search("泵")
    assert hits and "泵" in hits[0][2]


def test_factory_ontology_relations(tmp):
    """工厂级本体：关系建模 + 实体间导航（FDE 核心）。"""
    csvp = os.path.join(tmp, "equip.csv")
    with open(csvp, "w", encoding="utf-8") as f:
        f.write("id,device_type,line_id,status\n"
                "D001,空压机,A线,运行中\n"
                "D002,空压机,A线,待维护\n"
                "D003,泵,B线,运行中\n")
    relations = {
        "device_type": {"rel": "http://solo.local/ontology#hasType",
                        "target_class": "DeviceType", "label": "设备类型"},
        "line_id": {"rel": "http://solo.local/ontology#belongsToLine",
                    "target_class": "Line", "label": "属于产线"},
    }
    o = ontology_mod.Ontology()
    o.from_csv(csvp, entity_name="equip", id_col="id", relations=relations)
    o.build()

    # 实体间导航（对象属性）
    line = o.query("equip", "D001", "line_id")
    assert line == ["Line:A线"], f"line={line}"
    typ = o.query("equip", "D002", "device_type")
    assert typ == ["DeviceType:空压机"], f"typ={typ}"

    # 目标类已建（build 补全）
    assert "Line" in o.entities and "DeviceType" in o.entities

    # 待维护设备（结构化查询）
    maintain = [s.split(":")[-1] for s, p, v in o.triples
                if p.endswith("status") and v == "待维护"]
    assert maintain == ["D002"], f"maintain={maintain}"


def test_factory_multi_ontology(tmp):
    """多表工厂本体：设备+工单跨实体关联（FDE 工厂级核心）。"""
    # 设备表
    eq_csv = os.path.join(tmp, "equip.csv")
    with open(eq_csv, "w", encoding="utf-8") as f:
        f.write("id,device_type,status\nD001,空压机,运行中\nD002,泵,待维护\n")
    eq_rels = {"device_type": {"rel": "http://solo.local/ontology#hasType",
                               "target_class": "DeviceType", "label": "设备类型"}}
    # 工单表（equipment_id 外键→设备）
    wo_csv = os.path.join(tmp, "workorders.csv")
    with open(wo_csv, "w", encoding="utf-8") as f:
        f.write("wo_id,equipment_id,priority\nW001,D002,高\nW002,D001,中\n")
    wo_rels = {"equipment_id": {"rel": "http://solo.local/ontology#concernsEquipment",
                                "target_class": "factory_equipment", "label": "关联设备"}}

    o = ontology_mod.Ontology()
    o.from_csv(eq_csv, entity_name="factory_equipment", id_col="id", relations=eq_rels)
    o.from_csv(wo_csv, entity_name="factory_workorders", id_col="wo_id", relations=wo_rels)
    o.build()

    # 跨实体导航：工单→设备
    dev = o.query("factory_workorders", "W001", "equipment_id")
    assert dev == ["factory_equipment:D002"], f"dev={dev}"

    # 高优先工单关联的设备类型（多表问题解答）
    high_wo = [s.split(":")[-1] for s, p, v in o.triples
               if s.startswith("factory_workorders:") and p.endswith("priority") and v == "高"]
    assert high_wo == ["W001"], f"high={high_wo}"


# ---- skill：可复用经验 ----
def test_skill_match(tmp):
    s = skill_mod.Skill(dir=os.path.join(tmp, "skills"))
    s.add("写推文", ["公众号", "推文"], ["列大纲", "六维检查"])
    assert "写推文" in s.match("写一篇公众号推文")
    assert s.get("写推文")["version"] >= 1


# ---- writing：六维 ----
def test_writing_detects_ai_pattern():
    r = writing_mod.scan("通过这个赋能闭环，改善了很多。综上所述，很重要！")
    assert r["dimension_counts"]["D5"] >= 2  # 赋能+综上所述


# ---- code：影响分析 ----
def test_code_impact(tmp):
    # 建两个互相 import 的模块
    pkg = os.path.join(tmp, "pkg"); os.makedirs(pkg)
    with open(os.path.join(pkg, "a.py"), "w", encoding="utf-8") as f:
        f.write("from pkg import b\n\ndef fn_a():\n    return b.fn_b()\n")
    with open(os.path.join(pkg, "b.py"), "w", encoding="utf-8") as f:
        f.write("def fn_b():\n    return 1\n")
    cg = code_mod.CodeGraph()
    cg.index(pkg)
    imp = cg.impact("b.py")
    assert any("a.py" in f for f in imp), f"impact(b.py)={imp}"


def test_code_overview_explain(tmp):
    """代码库理解（FDE 接手项目能力）。"""
    pkg = os.path.join(tmp, "pkg"); os.makedirs(os.path.join(pkg, "core"))
    with open(os.path.join(pkg, "core", "main.py"), "w", encoding="utf-8") as f:
        f.write("from core import util\ndef run():\n    return util.helper()\n")
    with open(os.path.join(pkg, "core", "util.py"), "w", encoding="utf-8") as f:
        f.write("def helper():\n    return 1\n")
    cg = code_mod.CodeGraph()
    cg.index(pkg)
    ov = cg.overview()
    assert ov["files"] == 2 and ov["symbols"] >= 2
    ex = cg.explain("helper")
    assert ex.get("defined_in", "").endswith("util.py")
    assert any("main.py" in u for u in ex.get("used_by", []))


# ---- gen：FDE 代码/文档/审查 ----
def test_gen_signatures():
    """gen 模块：代码生成/文档/审查函数可调用，参数正确。"""
    import inspect
    from solo import gen
    assert callable(getattr(gen, "generate_code", None))
    assert callable(getattr(gen, "generate_doc", None))
    assert callable(getattr(gen, "review_code", None))
    sig = inspect.signature(gen.generate_doc)
    assert "kind" in sig.parameters and "topic" in sig.parameters


# ---- clean：工厂数据清洗 ----
def test_clean_dedup_missing_outlier(tmp):
    """清洗：去重/缺失/异常值处理。"""
    from solo.factory import clean as clean_mod
    rows = [
        {"id": "1", "temp": "45.2", "status": "运行"},
        {"id": "1", "temp": "45.2", "status": "运行"},  # 重复
        {"id": "2", "temp": "", "status": "运行"},      # 缺失
        {"id": "3", "temp": "45.3", "status": "运行"},
        {"id": "4", "temp": "45.4", "status": "运行"},
        {"id": "5", "temp": "45.1", "status": "运行"},
        {"id": "6", "temp": "80.0", "status": "运行"},  # 异常值
    ]
    cl = clean_mod.DataCleaner()
    out = cl.clean(rows, numeric_cols=["temp"], fill_missing="drop", outlier_method="iqr")
    assert cl.report["dropped_dup"] == 1
    assert cl.report["dropped_outlier"] == 1
    # 7 - 1去重 - 1缺失 - 1异常 = 4
    assert len(out) == 4


# ---- stats：工厂数据分析 ----
def test_stats_describe_and_anomaly():
    """分析：描述性统计 + 异常检测(IQR稳健) + SPC。"""
    from solo.factory import stats as stats_mod
    data = [45.2, 45.5, 45.1, 45.3, 45.4, 45.2, 58.9, 45.3]  # 含异常 58.9
    desc = stats_mod.describe(data)
    assert desc["count"] == 8 and "mean" in desc and "median" in desc
    # IQR 法稳健检测 58.9（zscore 会被离群点拉高 std 而不敏感）
    anom = stats_mod.detect_anomaly(data, method="iqr")
    assert any(abs(a["value"] - 58.9) < 0.1 for a in anom), f"anom={anom}"
    cc = stats_mod.control_chart(data)
    assert "ucl" in cc and "lcl" in cc
    assert cc["ucl"] > cc["lcl"]


# ---- task：状态控制面 ----
def test_task_lifecycle(tmp):
    t = task_mod.Task(dir=os.path.join(tmp, "tasks"))
    t.new("t1")
    t.add_step("t1", "step1")
    t.gate("t1", "决策门?")
    assert t.status("t1")["state"] == "waiting"
    t.resolve("t1")
    st = t.status("t1")
    assert st["state"] == "doing"
    assert all(g["resolved"] for g in st["gates"])
    t.predict("t1", "会更好")
    assert t.status("t1")["prediction"]["claim"] == "会更好"


# ---- provider：分级退出码 ----
def test_provider_no_key_auth_error():
    p = provider_mod.Provider(remote={"type": "openai-compatible", "base_url": "https://x",
                                      "model": "m", "api_key_env": "NONE_SUCH_ENV_XXX"})
    with pytest.raises(provider_mod.ProviderError) as ei:
        p.complete("本体建模", tier="remote")
    assert ei.value.code == provider_mod.EXIT_AUTH


def test_provider_local_down_network_error():
    p = provider_mod.Provider(local={"type": "ollama", "base_url": "http://127.0.0.1:9",
                                     "model": "x"})
    with pytest.raises(provider_mod.ProviderError) as ei:
        p.complete("hi", tier="local")
    assert ei.value.code == provider_mod.EXIT_NETWORK


# ---- provider：工厂本体风格 model_config.json + 智能路由 ----
def test_provider_from_config_new_json_style():
    """新格式 config/model_config.json（active/routing/models）应正确解析并保留路由。"""
    mc = {
        "active": "cloud",
        "routing": {"complex_models": ["cloud", "local"], "simple_models": ["local"],
                    "offline_fallback": True},
        "embedding": {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text"},
        "models": {
            "local": {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest", "api_key": ""},
            "cloud": {"type": "openai", "base_url": "https://api.deepseek.com", "model": "deepseek-chat", "api_key": ""},
        },
    }
    p = provider_mod.Provider.from_config(mc)
    assert p.active == "cloud"
    assert p.routing.get("complex_models") == ["cloud", "local"]
    assert p.local.get("model") == "ornith:latest"
    assert p.remote.get("model") == "deepseek-chat"
    assert p.embed_cfg.get("model") == "nomic-embed-text"
    # 空 api_key 被清理，不残留空字符串
    assert "api_key" not in p.remote


def test_provider_routing_simple_local_complex_cloud():
    """auto 路由：简单任务→local，复杂任务→cloud；active=local 恒走本地。"""
    mc = {
        "active": "cloud",
        "routing": {"complex_models": ["cloud", "local"], "simple_models": ["local"],
                    "offline_fallback": True},
        "models": {
            "local": {"type": "ollama", "model": "ornith:latest"},
            "cloud": {"type": "openai", "model": "deepseek-chat"},
        },
    }
    p = provider_mod.Provider.from_config(mc)
    assert p._pick("今天几号", "auto").get("model") == "ornith:latest"          # simple → local
    assert p._pick("帮我做本体建模并写方案", "auto").get("model") == "deepseek-chat"  # complex → cloud
    assert p._is_complex("写一篇深度分析报告") is True
    assert p._is_complex("你好") is False
    # active=local 时即使复杂任务也走本地
    p_local = provider_mod.Provider.from_config({**mc, "active": "local"})
    assert p_local._pick("做本体建模", "auto").get("model") == "ornith:latest"


def test_provider_model_config_json_file(tmp):
    """仓库内 config/model_config.json 应能被 load_model_config/load_config 读取（归一化）。"""
    import json
    mc = {
        "active": "cloud",
        "routing": {"policy": "simple->local", "complex_models": ["cloud"], "simple_models": ["local"]},
        "embedding": {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text"},
        "models": {
            "local": {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest"},
            "cloud": {"type": "openai", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
        },
    }
    path = os.path.join(tmp, "model_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mc, f, ensure_ascii=False)

    raw = provider_mod.load_model_config(path)
    assert raw["active"] == "cloud"
    assert raw["models"]["cloud"]["model"] == "deepseek-chat"
    # load_config 归一化为旧 provider 形状，供 agent/cli/web 兼容
    normalized = provider_mod.load_config(path)
    assert normalized["provider"]["local"]["model"] == "ornith:latest"
    assert normalized["provider"]["remote"]["model"] == "deepseek-chat"
    assert normalized["provider"]["embed"]["model"] == "nomic-embed-text"
