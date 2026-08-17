# -*- coding: utf-8 -*-
"""solo FDE 深度补强回归（对齐 10 核心原子 + 写作原子）。

覆盖 10 核心原子（真实数据）+ 写作原子（write-qa/write-evidence）+ 组装链 run_flow 全绿 + 边界断言：

  1. monitor.device : 时序异常检测（突跳/趋势） + 动态阈值
  2. predict.maintain: 预测性维护（RUL/风险等级）
  3. ontology.qa     : 本体确定性问答 + 知识检索（RAG，防幻觉）
  4. sme.decision    : SME 决策（确定性规则）
  5. diagnose.kb     : 故障知识库「add→search→根因」，未知症状诚实 miss（防幻觉）
  6. deliver.accept  : 交付验收闭环（需求→SRS→验收→勾稽→交付包→签收）
  7. write.qa        : 六维中文写作质量检查（D1-D6）+ AI味
  8. write.evidence  : 证据账本 + 事实核查（防幻觉、可溯源）
  9. 组装链 run_flow : fde-workflow.json 端到端全绿（含写作，accept=True）
 10. 边界铁律        : 算法开源联动、数据不出厂（linkage.status boundary 字段）

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
    """一次扫描+加载全原子（真实仓库树，含写作原子）。"""
    r = AgentRuntime()
    r.scan(tolerate=True)
    r.load(tolerate=True)
    return r


# ═══════════════════════════ 1. monitor.device 时序异常 + 动态阈值 ═══════════════════════════
class TestMonitorDevice:
    def test_sudden_spike_detected(self, rt):
        """平稳序列末尾突跳 8.6 应判为突跳异常（真实数据）。"""
        r = rt.run_capability("monitor.device", op="anomaly",
                              values=[5.0, 5.1, 5.0, 5.2, 5.1, 8.6], k=3.0)
        assert r["ok"], r.get("error")
        assert r["data"]["anomalies"], "应检出异常点"

    def test_flat_series_no_false_positive(self, rt):
        """平稳序列不得误报（边界：无异常应 miss）。"""
        r = rt.run_capability("monitor.device", op="anomaly",
                              values=[5.0, 5.0, 5.0, 5.0, 5.0, 5.0], k=3.0)
        assert r["ok"]
        assert r["data"]["anomalies"] == []

    def test_adaptive_threshold_real(self, rt):
        """动态阈值（MAD 稳健基线）应给出 upper/lower。"""
        d = tempfile.mkdtemp(prefix="mon_")
        r = rt.run_capability("monitor.device", op="adaptive",
                              values=[5.0, 5.1, 5.0, 5.2, 5.1, 5.3], k=3.0, dir=d)
        assert r["ok"]
        assert r["data"]["threshold"]["upper"] > r["data"]["threshold"]["lower"]


# ═══════════════════════════ 2. predict.maintain 预测性维护 ═══════════════════════════
class TestPredictMaintain:
    def test_risk_rul_positive_on_rising_trend(self, rt):
        """上升趋势应给出风险等级 + 有限 RUL（预测性维护雏形）。"""
        r = rt.run_capability("predict.maintain", op="risk",
                              series=[5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                              device_id="pump_01", k=3.0)
        assert r["ok"], r.get("error")
        risk = r["data"]["risk"]
        assert risk["level"], "应有风险等级"
        assert risk["next_maintain"]["rul"] > 0, "RUL 应为正"

    def test_forecast_real(self, rt):
        """趋势预测应产出 next 值。"""
        r = rt.run_capability("predict.maintain", op="forecast",
                              series=[4.0, 4.2, 4.5, 4.9, 5.2, 5.6])
        assert r["ok"]
        assert r["data"]["forecast"]["next"] is not None


# ═══════════════════════════ 3. ontology.qa 本体问答 + RAG ═══════════════════════════
class TestOntologyQa:
    def test_ask_aggregate_real_data(self, rt):
        """确定性聚合问答：count 真实命中。"""
        r = rt.run_capability("ontology.qa", op="ask",
                              rows=[{"id": "P001", "status": "运行中", "temp": 80},
                                    {"id": "P002", "status": "运行中", "temp": 90},
                                    {"id": "P003", "status": "停机", "temp": 40}],
                              question="一共有多少条记录")
        assert r["ok"]
        assert r["data"]["answer"]["value"] == 3

    def test_ask_filter_real_data(self, rt):
        """状态过滤问答：真实命中。"""
        r = rt.run_capability("ontology.qa", op="ask",
                              rows=[{"id": "P001", "status": "运行中", "temp": 80},
                                    {"id": "P002", "status": "运行中", "temp": 90},
                                    {"id": "P003", "status": "停机", "temp": 40}],
                              question="状态为运行中的设备")
        assert r["ok"]
        assert r["data"]["answer"]["value"] == 2

    def test_retrieve_hit(self, rt):
        """知识检索（RAG）：真实入库 → 命中。"""
        r = rt.run_capability("ontology.qa", op="retrieve",
                              rows=[{"id": "P001", "status": "运行中", "temp": 80},
                                    {"id": "P002", "status": "运行中", "temp": 90}],
                              question="运行中的设备", top_k=2)
        assert r["ok"]
        assert r["data"]["retrieved"], "应返回检索结果"


# ═══════════════════════════ 4. sme.decision 决策 ═══════════════════════════
class TestSmeDecision:
    def test_decide_real_data(self, rt):
        """sme 确定性决策（真实仓库数据）应产出多条决策。"""
        r = rt.run_capability("sme.decision", op="decide",
                              data={"inventory": [
                                  {"product_id": "P001", "stock": 5, "safety_stock": 14,
                                   "lead_time_days": 7}]},
                              industry="factory")
        assert r["ok"], r.get("error")
        assert r["data"]["total"] > 0
        assert r["data"]["decisions"], "应有决策清单"

    def test_decide_inventory_alert(self, rt):
        """低库存应触发补货/缺货决策（告警→决策→行动链）。"""
        r = rt.run_capability("sme.decision", op="decide",
                              data={"inventory": [
                                  {"product_id": "P001", "stock": 5, "safety_stock": 14}]})
        assert r["ok"]
        names = [d["name"] for d in r["data"]["decisions"]]
        assert any("补货" in n or "缺货" in n for n in names), f"未触发库存告警: {names}"


# ═══════════════════════════ 5. diagnose.kb 故障知识库 ═══════════════════════════
class TestDiagnoseKb:
    def _kbdir(self):
        return tempfile.mkdtemp(prefix="fde_diag_")

    def test_add_then_search_root_cause(self, rt):
        """add 沉淀知识 → search 命中 → 根因 + 方案。"""
        d = self._kbdir()
        ar = rt.run_capability("diagnose.kb", op="add", dir=d,
                               problem="水泵振动超限", solution="轴承磨损/泵轴对中不良",
                               signals=["vibration"])
        assert ar["ok"], ar.get("error")
        r = rt.run_capability("diagnose.kb", op="search", dir=d,
                              problem="水泵振动大", top_k=3)
        assert r["ok"]
        assert r["data"]["hit"], "应命中故障库"
        assert r["data"]["hit"]["solution"] == "轴承磨损/泵轴对中不良"

    def test_unknown_symptom_miss_anti_hallucination(self, rt):
        """从未见过的症状应诚实 miss（防幻觉），不编造根因。"""
        d = self._kbdir()
        rt.run_capability("diagnose.kb", op="add", dir=d,
                          problem="水泵振动超限", solution="轴承磨损")
        r = rt.run_capability("diagnose.kb", op="search", dir=d,
                              problem="完全没见过的新故障现象XYZ")
        assert r["ok"]
        assert r["data"]["hit"] is None, "未知症状不应命中"
        assert "miss" in r["data"]["note"].lower() or "无匹配" in r["data"]["note"]

    def test_suggest_fault_advice(self, rt):
        """维修建议 suggest 应产出动作清单。"""
        r = rt.run_capability("diagnose.kb", op="suggest", problem="振动越限")
        assert r["ok"]
        assert r["data"]["suggestions"], "应有维修建议"


# ═══════════════════════════ 6. deliver.accept 交付验收闭环 ═══════════════════════════
class TestDeliverAccept:
    def test_package_acceptance_loop(self, rt):
        """交付包：需求→SRS→验收→勾稽→交付包→签收（全闭环）。"""
        d = tempfile.mkdtemp(prefix="del_")
        r1 = rt.run_capability("deliver.accept", op="requirement", dir=d,
                               story="SPC判异能力上线，实现振动越限自动预警",
                               category="质量", priority="P0", req_id="R-001")
        assert r1["ok"], r1.get("error")
        r2 = rt.run_capability("deliver.accept", op="requirement", dir=d,
                               story="设备监测看板，支持实时振动趋势",
                               category="设备", priority="P1", req_id="R-002")
        reqs = [r1["data"]["requirement"], r2["data"]["requirement"]]
        acc = rt.run_capability("deliver.accept", op="acceptance",
                                requirements=reqs, dir=d)
        assert acc["ok"] and len(acc["data"]["acceptance_list"]) >= 2
        lst = acc["data"]["acceptance_list"]
        for i in lst:
            i["result"] = "通过"
        rec = rt.run_capability("deliver.accept", op="reconcile",
                                requirements=reqs, acceptance=lst, dir=d)
        assert rec["ok"] and rec["data"]["reconcile"]["ok"], "勾稽未通过!"
        pkg = rt.run_capability("deliver.accept", op="package", dir=d,
                                requirements=reqs, acceptance=lst,
                                monitor_snapshot={"devices": 2},
                                tickets=[{"id": "TK-001"}], kb="factory")
        assert pkg["ok"] and pkg["data"]["package"]["report"]["markdown"], "交付报告空壳!"
        v = rt.run_capability("deliver.accept", op="verify", acceptance=lst, dir=d)
        assert v["ok"] and v["data"]["accept"]["accept"] is True, "验收未全过!"


# ═══════════════════════════ 7. write.qa 写作质量检查 ═══════════════════════════
class TestWriteQa:
    def test_scan_six_dimension(self, rt):
        """六维检查：AI味词应被 D5 命中。"""
        r = rt.run_capability("write.qa", op="scan",
                              text="这是一个测试通过赋能闭环实现降维打击")
        assert r["ok"], r.get("error")
        report = r["data"]["report"]
        assert report["layers"]["D5"]["issue_count"] >= 1, "D5 未命中 AI 味词"
        assert isinstance(report["passed"], bool)

    def test_scan_clean_text_passes(self, rt):
        """干净文本应无 L1 必改（passed=True）。"""
        r = rt.run_capability("write.qa", op="scan",
                              text="泵站振动预警已上线，SPC判异可观测，振动越限自动告警。")
        assert r["ok"]
        assert r["data"]["passed"] is True, "干净文本不应有必改问题"

    def test_ai_taste_report(self, rt):
        """AI味自检：应返回 ai_score 与 verdict。"""
        r = rt.run_capability("write.qa", op="ai_taste",
                              text="这是一个测试通过赋能闭环实现降维打击", style="report")
        assert r["ok"]
        assert r["data"]["ai_score"] is not None


# ═══════════════════════════ 8. write.evidence 证据核查 ═══════════════════════════
class TestWriteEvidence:
    def test_fact_check_supported(self, rt):
        """事实核查：声明与真实数据源吻合 → supported。"""
        r = rt.run_capability("write.evidence", op="fact_check",
                              text="温度90度，共5台设备运行正常",
                              source_rows=[{"temperature": 90, "count": 5},
                                           {"temperature": 95, "count": 5}])
        assert r["ok"], r.get("error")
        s = r["data"]["summary"]
        assert s["supported"] >= 1, "声明应可溯源"
        assert s["contradicted"] == 0

    def test_fact_check_no_source_honest(self, rt):
        """无数据源时应诚实标 unsupported（防幻觉，不编造）。"""
        r = rt.run_capability("write.evidence", op="fact_check",
                              text="温度90度", source_rows=[])
        assert r["ok"]
        s = r["data"]["summary"]
        assert s["unsupported"] >= 1 or s["total"] == 0, "无源应诚实不可溯源"

    def test_build_ledger_extracts_claims(self, rt):
        """证据账本：应提取数字/百分比声明。"""
        r = rt.run_capability("write.evidence", op="build_ledger",
                              text="振动下降30%，温度90度")
        assert r["ok"]
        assert r["data"]["claims_n"] >= 1, "应提取至少 1 条声明"


# ═══════════════════════════ 9. 组装链 run_flow 端到端全绿（含写作） ═══════════════════════════
class TestLinkageFlow:
    def test_fde_workflow_all_green(self, rt):
        """fde-workflow.json 组装链全绿：monitor→spc→predict→decision→ticket→kb→maintain→write→accept→train。"""
        with open(os.path.join(_REPO, "assemblies", "fde-workflow.json"),
                  encoding="utf-8") as f:
            asm = json.load(f)
        wd = tempfile.mkdtemp(prefix="fde_link_")
        res = rt.run_flow(asm, workdir=wd)
        assert res["ok"]
        steps = res["data"]["steps"]
        assert steps, "组装链不应为空"
        for t in steps:
            assert t["ok"], f"步骤 {t['id']} 失败: {t.get('error')}"
        caps = [t["capability"] for t in steps]
        assert "monitor.device" in caps and "data.cap" in caps
        assert "predict.maintain" in caps and "sme.decision" in caps
        assert "diagnose.kb" in caps and "write.qa" in caps
        assert "write.evidence" in caps and "deliver.accept" in caps
        assert res["loop_closed"] is True
        final = res["data"]["final"]
        assert final["accept"] is True
        assert final["tickets_n"] >= 1, "应产出工单"
        assert final["writing_evidence_pass"] is True

    def test_fde_workflow_writing_steps_run(self, rt):
        """组装链内写作步骤：write-qa 与 write-evidence 应实际执行并产出。"""
        with open(os.path.join(_REPO, "assemblies", "fde-workflow.json"),
                  encoding="utf-8") as f:
            asm = json.load(f)
        wd = tempfile.mkdtemp(prefix="fde_link2_")
        res = rt.run_flow(asm, workdir=wd)
        steps = {t["id"]: t for t in res["data"]["steps"]}
        wq = steps["write_qa"]
        assert wq["ok"] and wq["data"]["report"]["total_issues"] >= 0
        we = steps["write_evidence"]
        assert we["ok"] and we["data"]["summary"]["total"] >= 0


# ═══════════════════════════ 10. 边界铁律：数据不出厂 ═══════════════════════════
class TestBoundary:
    def test_linkage_boundary_rule(self):
        """边界铁律：算法开源联动，数据不出厂。"""
        st = linkage.status()
        assert "boundary" in st
        assert "数据不出厂" in st["boundary"]

    def test_registry_has_diagnose_kb(self, rt):
        """registry 应识别并注册 diagnose-kb。"""
        assert "diagnose-kb" in rt.agents
        assert "diagnose.kb" in rt.capabilities()

    def test_registry_has_ten_core_atoms(self, rt):
        """10 核心原子应全部注册。"""
        caps = rt.capabilities()
        for c in ["monitor.device", "predict.maintain", "ontology.qa",
                  "sme.decision", "diagnose.kb", "fde.task", "data.cap",
                  "deliver.accept", "deliver.train", "memory.core"]:
            assert c in caps, f"能力 {c} 未注册"

    def test_registry_has_writing_atoms(self, rt):
        """写作原子 write-qa / write-evidence 应已注册并可用。"""
        caps = rt.capabilities()
        assert "write.qa" in caps, "write.qa 未注册"
        assert "write.evidence" in caps, "write.evidence 未注册"
