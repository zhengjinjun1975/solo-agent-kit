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
from solo import ontology as ontology_mod
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
    assert __version__ == "0.1.0"


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
