# -*- coding: utf-8 -*-
"""test_ops_diagram.py — P2：现场运维合并(factory/ops) + 图件(factory/diagram)。"""
from __future__ import annotations

import os
import tempfile

from solo.factory import ops
from solo.factory import diagram


# ---- ops：现场运维能力面（site 台账 + 资源监控 + SSH）----
def test_ops_site_ledger():
    """Site 台账：current_site / devices / resolve_device（现场定位锚点）。"""
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "site.json")
        # 预置厂区配置（台账）
        import json
        cfg = {"role": "laptop", "current_site": "华东厂区",
               "sites": {"华东厂区": {"devices": [
                   {"name": "plc1", "host": "192.168.1.10", "user": "ops", "port": 22}]}}}
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        s = ops.Site(file=f)
        assert s.current_site == "华东厂区"
        assert s.devices() == [{"name": "plc1", "host": "192.168.1.10", "user": "ops", "port": 22}]
        assert s.resolve_device("plc1")["ok"] is True
        assert s.resolve_device("ghost")["ok"] is False


def test_ops_resolve_device_and_monitor():
    """Site.resolve_device 台账解析 + system_stats 本机监控（结构完整）。"""
    with tempfile.TemporaryDirectory() as td:
        import json
        f = os.path.join(td, "site.json")
        cfg = {"role": "laptop", "current_site": "A",
               "sites": {"A": {"devices": [{"name": "plc1", "host": "10.0.0.5"}]}}}
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        s = ops.Site(file=f)
        r = s.resolve_device("plc1")
        assert r["ok"] is True and r["device"]["host"] == "10.0.0.5"
    # 本机监控：结构必须完整（psutil 缺失时降级）
    stats = ops.system_stats()
    assert "cpu" in stats and "memory" in stats and "processes" in stats


def test_ops_resolve_conn_host_pass_through():
    """_resolve_conn：未知名（非台账设备）原样返回 host，向后兼容直传。"""
    h, u, p, dev = ops._resolve_conn("192.168.1.99", "ops", 22)
    assert h == "192.168.1.99" and u == "ops" and p == 22 and dev == "192.168.1.99"


def test_ops_site_no_file_defaults():
    """无台账文件时 Site 默认空（不崩溃）。"""
    s = ops.Site(file=os.path.join(tempfile.gettempdir(), "_nonexistent_site_x.json"))
    assert s.current_site == ""
    assert s.devices() == []
    assert s.resolve_device("x")["ok"] is False


# ---- diagram：图件（ER / 流程 / 状态）----
def test_diagram_flow():
    """流程图：survey 四阶段产 Mermaid，含首尾节点与连线。"""
    src = diagram.flow_diagram()
    assert src.startswith("flowchart LR")
    for ph in ("采集", "结构化", "SRS", "验收"):
        assert ph in src
    assert "--> " in src
    assert src.count("-->") == 3  # 四阶段 → 3 条边


def test_diagram_state():
    """状态图：task 五态产 Mermaid。"""
    src = diagram.state_diagram()
    assert src.startswith("stateDiagram-v2")
    assert "todo" in src and "done" in src
    assert "[*] -->" in src


def test_diagram_er():
    """ER 图：从 ontology 实体/关系产出实体块 + 关系边。"""
    from solo.factory import ontology as ont_mod
    o = ont_mod.Ontology()
    with tempfile.TemporaryDirectory() as td:
        csvp = os.path.join(td, "d.csv")
        with open(csvp, "w", encoding="utf-8") as fh:
            fh.write("id,temp,sensor_id\n1,36.5,d1\n2,37.0,d2\n")
        o.from_csv(csvp, entity_name="设备")
    o.build()
    src = diagram.er_diagram(o)
    assert src.startswith("erDiagram")
    assert "设备" in src


def test_diagram_build_empty_er():
    """build 一键产出：无 ontology 时 ER 为空模板，flow/state 有默认。"""
    r = diagram.build(ontology=None)
    assert r["er"].startswith("erDiagram")
    assert "flowchart LR" in r["flow"]
    assert "stateDiagram-v2" in r["state"]
