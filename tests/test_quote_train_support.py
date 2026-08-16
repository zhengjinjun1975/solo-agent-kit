# -*- coding: utf-8 -*-
"""solo.factory quote/train/support（商务报价/培训材料/工单运维）单测。

覆盖 FDE 全域能力：
  quote   质量分 / 人天估算 / 报价单 / 导出xlsx
  train   操作手册 / FAQ
  support 工单状态机 / 监控告警建单 / 运维知识库

跑法：python -m pytest tests/test_quote_train_support.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.factory import quote, train, support  # noqa: E402
from solo.factory.data import quality  # noqa: E402


def _dirty_rows():
    """构造脏数据：缺失/重复/异常值 齐全。"""
    return [
        {"id": "1", "temp_c": "20", "status": "运行"},
        {"id": "1", "temp_c": "20", "status": "运行"},   # 重复
        {"id": "2", "temp_c": "", "status": "运行"},     # 缺失
        {"id": "3", "temp_c": "9999", "status": "运行"}, # 异常
        {"id": "4", "temp_c": "22", "status": "停机"},
    ]


def _clean_rows():
    return [{"id": str(i), "temp_c": str(20 + i), "status": "运行"} for i in range(100)]


# ═══════════════════════════ 1. 商务报价 quote ═══════════════════════════
class TestQuote:
    def test_quality_score_dirty_lower_than_clean(self):
        qd = quote.quality_score(_dirty_rows())
        qc = quote.quality_score(_clean_rows())
        assert 0.0 <= qd <= 1.0
        assert qd < qc, f"脏数据质量分应更低: {qd} vs {qc}"

    def test_quality_score_clean_high(self):
        assert quote.quality_score(_clean_rows()) >= 0.9

    def test_quality_score_empty_zero(self):
        assert quote.quality_score([]) == 0.0

    def test_quality_level_tiers(self):
        assert quote.quality_level(0.95) == "优"
        assert quote.quality_level(0.8) == "良"
        assert quote.quality_level(0.7) == "中"
        assert quote.quality_level(0.5) == "差"

    def test_estimate_effort_structure(self):
        e = quote.estimate_effort(_clean_rows(), requirements=[{}] * 3, complexity="medium")
        assert set(e) >= {"rows", "requirements", "complexity", "quality",
                          "quality_level", "breakdown", "total_days"}
        assert e["requirements"] == 3
        assert e["complexity"] == "medium"
        assert e["total_days"] > 0

    def test_estimate_effort_invalid_complexity(self):
        with pytest.raises(ValueError):
            quote.estimate_effort(complexity="ultra")

    def test_estimate_effort_dirty_costs_more(self):
        e_clean = quote.estimate_effort(_clean_rows(), complexity="basic")
        e_dirty = quote.estimate_effort(_dirty_rows(), complexity="basic")
        assert e_dirty["total_days"] > e_clean["total_days"]

    def test_estimate_effort_complexity_raises_cost(self):
        e_basic = quote.estimate_effort(_clean_rows(), complexity="basic")
        e_adv = quote.estimate_effort(_clean_rows(), complexity="advanced")
        assert e_adv["total_days"] > e_basic["total_days"]

    def test_build_quote_structure(self):
        q = quote.build_quote("工厂数据中台", "数据清洗+看板", rows=_dirty_rows(),
                              requirements=[{}] * 2, complexity="medium")
        assert q["project"] == "工厂数据中台"
        assert q["totals"]["total"] > q["totals"]["subtotal"] > 0  # 含税
        assert len(q["lines"]) >= 2
        assert q["totals"]["days"] == q["effort"]["total_days"]
        assert "付款" in q["terms"]

    def test_build_quote_with_passed_effort(self):
        e = quote.estimate_effort(_clean_rows())
        q = quote.build_quote("P", "范围", effort=e)
        assert q["totals"]["days"] == e["total_days"]

    def test_export_quote_xlsx(self, tmp_path):
        q = quote.build_quote("报价项目A", "范围", rows=_clean_rows())
        out = quote.export_quote(q, path=str(tmp_path / "quote.xlsx"))
        # openpyxl 可用时应真生成；不可用则降级返回 ok=False
        assert out["ok"] in (True, False)
        if out["ok"]:
            assert out["total"] == q["totals"]["total"]
            assert os.path.exists(tmp_path / "quote.xlsx")
        else:
            assert "error" in out

    def test_export_quote_report_in_plugin(self):
        from solo.plugins import excel_report
        assert hasattr(excel_report, "quote_report")


# ═══════════════════════════ 2. 培训材料 train ═══════════════════════════
class TestTrain:
    def test_manual_default_capabilities(self):
        m = train.manual()
        assert m["title"] == "系统操作手册"
        assert m["sections"] > 0
        assert m["steps"] >= m["sections"] * 6
        assert "功能操作步骤" in m["markdown"]
        assert "scan" in m and "ai" in m

    def test_manual_explicit_caps_and_reqs(self):
        caps = {"factory": {"clean": {"desc": "数据清洗", "enabled": True},
                            "stats": {"desc": "数据分析", "enabled": True}}}
        reqs = [{"id": "R-001", "title": "自动对账", "category": "生产",
                 "story": "库存盘点耗时"}]
        m = train.manual(capabilities=caps, requirements=reqs)
        assert m["sections"] == 2
        assert "自动对账" in m["markdown"]      # 需求 → 使用场景
        assert "数据清洗" in m["markdown"]
        assert "R-001" in m["markdown"]

    def test_manual_caps_without_desc(self):
        m = train.manual(capabilities={"g": {"x": {}}})
        assert "x" in m["markdown"]

    def test_faq_basic(self):
        f = train.faq()
        assert f["count"] >= 3
        assert "Q1" in f["markdown"]
        assert "# " in f["markdown"]

    def test_faq_custom(self):
        f = train.faq([{"q": "如何重启？", "a": "重启服务"}], title="设备FAQ")
        assert f["count"] == 1
        assert "如何重启" in f["markdown"]
        assert "设备FAQ" in f["markdown"]


# ═══════════════════════════ 3. 工单运维 support ═══════════════════════════
class TestSupportTicket:
    def test_lifecycle(self, tmp_path):
        st = support.SupportTicket(dir=str(tmp_path))
        t = st.new("系统部署失败，服务无法启动", severity="high")
        tid = t["id"]
        assert t["state"] == "新建"
        assert t["triage"] == "部署类"
        assert st.status(tid)["state"] == "新建"

        st.process(tid, "检查部署日志，定位到端口占用")
        assert st.status(tid)["state"] == "处理中"

        st.resolve(tid, "释放占用端口后重启服务")
        assert st.status(tid)["state"] == "已解决"

        st.close(tid)
        assert st.status(tid)["state"] == "关闭"

    def test_list_filter_by_state(self, tmp_path):
        st = support.SupportTicket(dir=str(tmp_path))
        st.new("内存不足")
        t2 = st.new("磁盘IO过高")
        st.resolve(t2["id"], "清理日志")
        states = [i["state"] for i in st.list()]
        assert "新建" in states and "已解决" in states
        assert all(i["state"] == "已解决" for i in st.list(state="已解决"))

    def test_resolve_sinks_to_kb(self, tmp_path):
        st = support.SupportTicket(dir=str(tmp_path))
        t = st.new("数据库连接超时")
        st.resolve(t["id"], "扩容连接池并增加超时")
        kb = support.KnowledgeBase(os.path.join(str(tmp_path), "kb"))
        # resolve 已自动沉淀知识库
        found = kb.search("数据库连接超时", top_k=1)
        assert found, "解决后应自动沉淀运维知识库"

    def test_process_rejects_closed(self, tmp_path):
        st = support.SupportTicket(dir=str(tmp_path))
        t = st.new("小故障")
        st.close(t["id"])
        r = st.process(t["id"], "再处理")
        assert "error" in r


class TestAlarmTickets:
    def test_creates_tickets_for_anomalies(self, tmp_path):
        monitor = {
            "ok": True, "site": "A", "count": 3,
            "devices": [
                {"name": "d1", "ok": True, "cpu_percent": 95.0, "mem_percent": 30.0},
                {"name": "d2", "ok": True, "cpu_percent": 40.0, "mem_percent": 95.0},
                {"name": "d3", "ok": False, "error": "连接失败"},
            ],
        }
        support.SupportTicket(dir=str(tmp_path))  # 确保目录可建
        # 用独立工单目录避免污染全局
        orig = support.DEFAULT_TICKET_DIR
        support.DEFAULT_TICKET_DIR = str(tmp_path)
        try:
            r = support.alarm_tickets(monitor)
        finally:
            support.DEFAULT_TICKET_DIR = orig
        assert r["created"] == 3           # d1 cpu / d2 mem / d3 连接
        types = sorted(a["type"] for a in r["alarms"])
        assert types == ["connection", "cpu", "mem"]
        # 连接失败工单 severity 最高
        conn = next(t for t in r["tickets"]
                    if t["problem"].startswith("设备 d3"))
        assert conn["severity"] == "high"

    def test_no_anomaly_no_ticket(self, tmp_path):
        monitor = {"ok": True, "devices": [
            {"name": "d1", "ok": True, "cpu_percent": 30.0, "mem_percent": 40.0}]}
        orig = support.DEFAULT_TICKET_DIR
        support.DEFAULT_TICKET_DIR = str(tmp_path)
        try:
            r = support.alarm_tickets(monitor)
        finally:
            support.DEFAULT_TICKET_DIR = orig
        assert r["created"] == 0

    def test_no_devices_returns_error(self, tmp_path):
        r = support.alarm_tickets({"ok": False, "error": "无设备台账"})
        assert r["created"] == []
        assert "error" in r


class TestKnowledgeBase:
    def test_add_dedup_and_search(self, tmp_path):
        kb = support.KnowledgeBase(str(tmp_path))
        assert kb.add("温度异常", "校准传感器") is True
        assert kb.add("温度异常", "校准传感器") is False   # 去重
        assert kb.add("内存泄漏", "重启容器") is True
        assert len(kb.all()) == 2
        hits = kb.search("温度波动", top_k=1)
        assert hits and "温度" in hits[0]["text"]

    def test_uses_memory_underlying(self, tmp_path):
        from solo import memory as mem_mod
        kb = support.KnowledgeBase(str(tmp_path))
        kb.add("A", "B")
        m = mem_mod.Memory(str(tmp_path))
        # P1 增量写：add_fact 写入追加日志(facts.jsonl)，读经合并视图可见
        assert len(m._load_facts()) == 1
