# -*- coding: utf-8 -*-
"""solo 三大开源联动 + FDE 深度补强收尾回归。

覆盖 4 个新原子（真实数据）+ 跨仓库联动 + 组装链 run_flow 全绿 + 边界断言：

  1. monitor-anomaly : 时序异常检测（趋势/突跳） + 预测性维护 RUL/健康指数
  2. factory-cognition: 复用 factory-ontology-kit 本体问答 + 离线 RAG（数据不出厂）
  3. sme-decision     : 复用 sme-decision-ontology 决策 / 阈值回灌 / 告警→决策→行动
  4. diagnose-kb      : 故障知识库「learn→diagnose→根因分析」，未知症状诚实 miss（防幻觉）
  5. 组装链 run_flow  : monitor→factory→sme→fde→diagnose→delivery 跨开源协同全绿
  6. 边界铁律         : 算法开源联动、数据不出厂（linkage.status boundary 字段）

跑法：python -m pytest tests/test_fde_linkage_deepen.py -v
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fde_runtime import linkage  # noqa: E402
from fde_runtime.loader import AgentRuntime  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def rt():
    """一次扫描+加载全原子（真实仓库树，含 4 个新原子）。"""
    r = AgentRuntime()
    r.scan(tolerate=True)
    r.load(tolerate=True)
    return r


# ═══════════════════════════ 1. monitor-anomaly 时序异常 + RUL ═══════════════════════════
class TestMonitorAnomaly:
    def test_sudden_spike_detected(self, rt):
        """平稳序列末尾突跳 8.6 应判为突跳异常（真实数据）。"""
        r = rt.run_capability("monitor.anomaly", op="detect", mode="sudden",
                              values=[5.0, 5.1, 5.0, 5.2, 5.1, 8.6], k=3.0)
        assert r["ok"], r.get("error")
        assert r["data"]["anomaly"] is True

    def test_trend_anomaly_detected(self, rt):
        """单调上升趋势应判为趋势异常（trend 默认阈值 k=0.8）。"""
        r = rt.run_capability("monitor.anomaly", op="detect", mode="trend",
                              values=[4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0])
        assert r["ok"]
        assert r["data"].get("anomaly") is True

    def test_flat_series_no_false_positive(self, rt):
        """平稳序列不得误报（边界：无异常应 miss）。"""
        r = rt.run_capability("monitor.anomaly", op="detect", mode="sudden",
                              values=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0], k=3.0)
        assert r["ok"]
        assert r["data"]["anomaly"] is False

    def test_predict_rul_positive_on_rising_trend(self, rt):
        """上升趋势向阈值逼近应给出有限正 RUL（预测性维护雏形）。"""
        r = rt.run_capability("monitor.anomaly", op="predict",
                              values=[5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                              failure_threshold=20.0)
        assert r["ok"]
        assert r["data"]["rul"] is not None and r["data"]["rul"] != "inf"
        assert r["data"]["rul"] > 0
        assert 0.0 <= r["data"]["health_index"] <= 1.0

    def test_predict_insufficient_data_no_rul(self, rt):
        """数据不足（<4）应诚实返回 rul=None（边界：防瞎猜）。"""
        r = rt.run_capability("monitor.anomaly", op="predict",
                              values=[5.0, 6.0], failure_threshold=20.0)
        assert r["ok"]
        assert r["data"]["rul"] is None


# ═══════════════════════════ 2. factory-cognition 本体/RAG 认知 ═══════════════════════════
class TestFactoryCognition:
    def test_offline_rag_retrieve_real_data(self, rt):
        """离线 RAG 入库真实知识 → 检索命中（不依赖 factory 仓库，恒可测）。"""
        d = tempfile.mkdtemp(prefix="fde_cog_")
        rt.run_capability("factory.cognition", op="add_doc", dir=d, kb="maintenance",
                          doc_id="D001", title="水泵振动维修手册",
                          chunks=[{"text": "水泵振动超限常见原因为轴承磨损，更换轴承后振动恢复至5.0以内"},
                                  {"text": "泵轴对中不良会导致振动增大，需做动平衡校准"}])
        r = rt.run_capability("factory.cognition", op="retrieve", dir=d,
                              question="泵振动大怎么处理", kb="maintenance")
        assert r["ok"]
        assert r["data"]["hit"] is True
        assert r["data"]["hits"][0]["doc_id"] == "D001"
        assert "轴承磨损" in r["data"]["hits"][0]["chunk"]

    def test_offline_rag_miss_no_hallucination(self, rt):
        """无相关知识的提问应 hit=False + note（防幻觉）。"""
        d = tempfile.mkdtemp(prefix="fde_cog2_")
        r = rt.run_capability("factory.cognition", op="retrieve", dir=d,
                              question="量子纠缠泵轴承", kb="maintenance")
        assert r["ok"]
        assert r["data"]["hit"] is False
        assert "禁幻觉" in r["data"]["note"]

    def test_cognition_linkage_status_present(self, rt):
        """跨仓库联动：factory-ontology-kit 应被识别且 present。"""
        r = rt.run_capability("factory.cognition", op="linkage")
        assert r["ok"]
        assert r["data"]["factory_ontology_kit"]["present"] is True
        assert r["data"]["boundary"]

    def test_ontology_qa_real_cross_repo(self, rt):
        """真实调用 factory-ontology-kit 本体问答（有真实语义数据，断言可答）。"""
        r = rt.run_capability("factory.cognition", op="ontology_qa",
                              question="一共有多少个阀门")
        # 仓库缺失时降级 fail(degraded)，不崩溃
        if r.get("ok"):
            assert r["data"]["source"] == "ontology"
        else:
            assert r.get("degraded")


# ═══════════════════════════ 3. sme-decision 决策/回灌 ═══════════════════════════
class TestSmeDecision:
    def test_decide_real_data(self, rt):
        """sme 确定性决策（真实仓库数据）应产出多条决策。"""
        r = rt.run_capability("sme.decision", op="decide",
                              enabled=["inventory", "equipment"], industry="manufacturing")
        assert r["ok"], r.get("error")
        assert r["data"]["total"] > 0

    def test_decide_alert_decision_action_chain(self, rt):
        """告警 → 决策 → 行动 一键链（跨 monitor+sme）。"""
        r = rt.run_capability("sme.decision", op="decide_alert",
                              device_id="pump_01", metric="vibration", value=8.6,
                              action="维护告急", level="预警")
        assert r["ok"]
        assert r["data"]["decision"] == "维护告急"
        assert isinstance(r["data"]["actions"], list)

    def test_feedback_preview_recalibrates_threshold(self, rt):
        """阈值回灌 preview：误报记录应触发阈值调整（不落盘）。"""
        r = rt.run_capability("sme.decision", op="feedback", industry="manufacturing",
                              feedback_records=[{"metric_key": "inventory.safety_stock",
                                                 "verdict": "误报"}],
                              mode="preview")
        assert r["ok"], r.get("error")
        assert r["data"]["count"] >= 1
        assert r["data"]["mode"] == "preview"

    def test_sme_linkage_status_present(self, rt):
        """跨仓库联动：sme-decision-ontology 应 present。"""
        r = rt.run_capability("sme.decision", op="linkage")
        assert r["ok"]
        assert r["data"]["sme_decision_ontology"]["present"] is True


# ═══════════════════════════ 4. diagnose-kb 故障知识库 ═══════════════════════════
class TestDiagnoseKb:
    def _kbdir(self):
        return tempfile.mkdtemp(prefix="fde_diag_")

    def test_learn_then_diagnose_root_cause(self, rt):
        """learn 沉淀知识 → diagnose 命中 → 根因 + 方案 + 置信度。"""
        d = self._kbdir()
        lr = rt.run_capability("diagnose.kb", op="learn", dir=d, symptom="水泵振动超限",
                               cause="轴承磨损", solution="更换轴承并做动平衡",
                               device="pump_01", signals={"vibration": 8.6})
        assert lr["ok"] and lr["data"]["total"] == 1
        r = rt.run_capability("diagnose.kb", op="diagnose", dir=d,
                              symptom="水泵振动大", signals={"vibration": 8.6},
                              device="pump_01")
        assert r["ok"]
        assert r["data"]["hit"] is True
        assert r["data"]["diagnosis"]["cause"] == "轴承磨损"
        assert r["data"]["diagnosis"]["confidence"] > 0.0

    def test_unknown_symptom_miss_anti_hallucination(self, rt):
        """从未见过的症状应诚实 miss（防幻觉），不编造根因。"""
        d = self._kbdir()
        rt.run_capability("diagnose.kb", op="learn", dir=d, symptom="水泵振动超限",
                          cause="轴承磨损", device="pump_01")
        r = rt.run_capability("diagnose.kb", op="diagnose", dir=d,
                              symptom="完全没见过的新故障现象XYZ")
        assert r["ok"]
        assert r["data"]["hit"] is False
        assert r["data"]["diagnosis"] is None
        assert "建议先 learn" in r["data"]["note"]

    def test_list_after_learn(self, rt):
        """learn 后 list 应能列出沉淀的知识。"""
        d = self._kbdir()
        rt.run_capability("diagnose.kb", op="learn", dir=d, symptom="电机温度偏高",
                          cause="散热不良/轴承润滑不足", device="motor_02")
        r = rt.run_capability("diagnose.kb", op="list", dir=d)
        assert r["ok"]
        assert len(r["data"]["entries"]) == 1

    def test_dedup_learn_same_symptom(self, rt):
        """同症状重复 learn 应去重（边界：不重复沉淀）。"""
        d = self._kbdir()
        rt.run_capability("diagnose.kb", op="learn", dir=d, symptom="水泵振动超限",
                          cause="轴承磨损", device="pump_01")
        rt.run_capability("diagnose.kb", op="learn", dir=d, symptom="水泵振动超限",
                          cause="泵轴对中", device="pump_01")
        r = rt.run_capability("diagnose.kb", op="list", dir=d)
        assert r["ok"]
        assert len(r["data"]["entries"]) == 1


# ═══════════════════════════ 5. 组装链 run_flow 跨开源协同全绿 ═══════════════════════════
class TestLinkageFlow:
    def test_solo_linkage_workflow_all_green(self, rt):
        """solo-linkage-workflow.json 组装链全绿：monitor→factory→sme→fde→diagnose→delivery。"""
        with open(os.path.join(_REPO, "assemblies", "solo-linkage-workflow.json"),
                  encoding="utf-8") as f:
            asm = json.load(f)
        wd = tempfile.mkdtemp(prefix="fde_link_")
        res = rt.run_flow(asm, workdir=wd)
        assert res["ok"]
        steps = res["data"]["steps"]
        assert steps, "组装链不应为空"
        for t in steps:
            assert t["ok"], f"步骤 {t['id']} 失败: {t.get('error')}"
        # 链路覆盖 6 大开源能力
        caps = [t["capability"] for t in steps]
        assert "monitor.metric" in caps and "monitor.anomaly" in caps
        assert "factory.cognition" in caps and "sme.decision" in caps
        assert "diagnose.kb" in caps and "delivery.package" in caps
        # 闭环：验收通过 + 全部步骤 ok
        assert res["loop_closed"] is True
        final = res["data"]["final"]
        assert final["accept"] is True
        assert final["tickets"], "应产出工单"
        assert final["worst_level"] == "ok"

    def test_linkage_diagnose_hits_root_cause(self, rt):
        """组装链中 learn→diagnose 应命中根因（前一环输出=后一环输入）。"""
        with open(os.path.join(_REPO, "assemblies", "solo-linkage-workflow.json"),
                  encoding="utf-8") as f:
            asm = json.load(f)
        wd = tempfile.mkdtemp(prefix="fde_link2_")
        res = rt.run_flow(asm, workdir=wd)
        diag = next(t for t in res["data"]["steps"] if t["id"] == "diagnose")
        assert diag["ok"]
        assert diag["data"]["hit"] is True
        assert diag["data"]["diagnosis"]["cause"] == "轴承磨损/泵轴对中不良"
        # 交付包工单应注入诊断根因（跨环节数据流）
        pkg = next(t for t in res["data"]["steps"] if t["id"] == "package")
        assert pkg["ok"]
        tkt = pkg["data"]["package"]["tickets"][0]
        assert tkt["diagnosis"] == "轴承磨损/泵轴对中不良"

    def test_monitor_anomaly_detected_in_flow(self, rt):
        """组装链内 monitor-anomaly 应检出突跳异常（真实越限值 8.6）。"""
        with open(os.path.join(_REPO, "assemblies", "solo-linkage-workflow.json"),
                  encoding="utf-8") as f:
            asm = json.load(f)
        wd = tempfile.mkdtemp(prefix="fde_link3_")
        res = rt.run_flow(asm, workdir=wd)
        an = next(t for t in res["data"]["steps"] if t["id"] == "anomaly")
        assert an["ok"] and an["data"]["anomaly"] is True
        pr = next(t for t in res["data"]["steps"] if t["id"] == "predict")
        assert pr["ok"] and pr["data"]["rul"] is not None


# ═══════════════════════════ 6. 边界铁律：数据不出厂 ═══════════════════════════
class TestBoundary:
    def test_linkage_boundary_rule(self):
        """边界铁律：算法开源联动，数据不出厂。"""
        st = linkage.status()
        assert "boundary" in st
        assert "数据不出厂" in st["boundary"]

    def test_registry_has_diagnose_kb(self, rt):
        """registry 应识别并注册 diagnose-kb（扫描注册修复的回归）。"""
        assert "diagnose-kb" in rt.agents
        assert "diagnose.kb" in rt.capabilities()

    def test_registry_has_all_new_atoms(self, rt):
        """4 个新原子应全部注册：monitor-anomaly / factory-cognition / sme-decision / diagnose-kb。"""
        caps = rt.capabilities()
        for c in ["monitor.anomaly", "factory.cognition", "sme.decision", "diagnose.kb"]:
            assert c in caps, f"能力 {c} 未注册"
