# -*- coding: utf-8 -*-
"""solo.factory.monitor（设备监测 P0，借鉴 DataBuff 骨架）单测。

覆盖 DataBuff 同构能力：
  MetricStore  统一指标存储（record/series/latest/aggregate 分钟预聚合）
  AlertEngine  阈值告警 / 突变检测 / 恢复自动关闭 / 告警→工单
  工单状态机   open → in_progress → done（合法流转 + 非法流转拒绝）
  Source       MQTT接入抽象（Mock 源跑通 数据→存储→告警→工单 全链路）
  MonitorAsk   AI问数（自然语言查设备/告警/工单，确定性路由先查库）

跑法：python -m pytest tests/test_monitor.py -v
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.factory.monitor import (  # noqa: E402
    MetricStore, AlertEngine, MonitorAsk, MockSensor, Source)


@pytest.fixture()
def store():
    """隔离临时存储目录（不污染 ~/.solo/monitor）。"""
    d = tempfile.mkdtemp(prefix="monitor_test_")
    return MetricStore(d)


@pytest.fixture()
def engine(store):
    return AlertEngine(store)


# ═══════════════════════════ 1. 统一指标存储 ═══════════════════════════
class TestMetricStore:
    def test_record_and_series(self, store):
        store.record("d1", "temperature", 45.0)
        store.record("d1", "temperature", 50.0)
        s = store.series("d1", "temperature")
        assert len(s) == 2
        assert s[0]["value"] == 45.0
        assert s[1]["value"] == 50.0
        assert store.latest("d1", "temperature")["value"] == 50.0

    def test_aggregate_minute_bucket(self, store):
        for v in [45, 46, 47]:
            store.record("d1", "temperature", v)
        agg = store.aggregate("d1", "temperature")
        assert agg, "分钟预聚合应有结果"
        assert len(agg) == 1
        assert agg[0]["avg"] == pytest.approx(46.0, abs=0.1)
        assert agg[0]["count"] == 3

    def test_ingest_payload_and_list(self, store):
        store.ingest({"device_id": "d1", "metric": "power", "value": 30})
        store.ingest({"device_id": "d2", "metric": "power", "value": 25})
        assert set(store.devices()) == {"d1", "d2"}


# ═══════════════════════════ 2. 告警评估引擎 ═══════════════════════════
class TestAlertEngine:
    def test_threshold_trigger(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0, level="high")
        raised = engine.evaluate_point("d1", "temperature", 90.0)
        assert len(raised) == 1
        assert raised[0]["state"] == "firing"
        assert raised[0]["type"] == "threshold"

    def test_no_trigger_below_threshold(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0)
        raised = engine.evaluate_point("d1", "temperature", 70.0)
        assert raised == []

    def test_mutate_detection(self, store, engine):
        # 基线 40± 连续 6 条，然后突跳 90 → 突变检测触发（pct=20）
        store.set_rule("d1", "temperature", ">", 200.0,  # 阈值不触发
                       mutate_pct=20.0)
        for v in [40, 41, 39, 42, 40, 41]:
            store.record("d1", "temperature", v)
        engine.evaluate_point("d1", "temperature", 90.0)
        assert store.alerts("firing"), "突变检测应触发告警"
        a = store.alerts("firing")[0]
        assert a["type"] == "mutate"

    def test_recovery_auto_close(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0)
        engine.evaluate_point("d1", "temperature", 90.0)
        assert store.alerts("firing")
        # 恢复
        engine.evaluate_point("d1", "temperature", 70.0)
        firing = store.alerts("firing")
        recovered = store.alerts("recovered")
        assert not firing
        assert len(recovered) == 1
        assert recovered[0]["recovered_at"] is not None


# ═══════════════════════════ 3. 工单状态机 open→in_progress→done ═══════════════════════════
class TestWorkflow:
    def test_alert_to_ticket_and_state_machine(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0)
        raised = engine.evaluate_point("d1", "temperature", 90.0)
        t = engine.alert_to_ticket(raised[0])
        assert t["state"] == "open"
        assert len(store.tickets("open")) == 1
        # open → in_progress
        t = engine.ticket_state(t["id"], "in_progress", "已派工")
        assert t["state"] == "in_progress"
        # in_progress → done
        t = engine.ticket_state(t["id"], "done", "处理完成")
        assert t["state"] == "done"
        assert t["done_at"]

    def test_illegal_transition_rejected(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0)
        raised = engine.evaluate_point("d1", "temperature", 90.0)
        t = engine.alert_to_ticket(raised[0])
        # open 不能直接跳 ... done 前必须先 in_progress 之外的非法: open→(done 允许, 但 open→done 直接)
        # 这里验证非法流转: done → open 被拒
        engine.ticket_state(t["id"], "done")
        r = engine.ticket_state(t["id"], "open")  # done 不能回 open
        assert "error" in r

    def test_recovery_closes_ticket(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0)
        raised = engine.evaluate_point("d1", "temperature", 90.0)
        engine.alert_to_ticket(raised[0])
        assert store.tickets("open")
        # 恢复 → 自动关闭工单
        engine.evaluate_point("d1", "temperature", 70.0)
        assert not store.tickets("open")
        assert store.tickets("done")


# ═══════════════════════════ 4. MQTT 接入抽象 Source ═══════════════════════════
class TestSource:
    def test_mock_source_full_chain(self, store):
        # 规则 + Mock 源跑通 数据→存储→告警→工单
        eng = AlertEngine(store)
        store.set_rule("d1", "temperature", ">", 80.0, level="high")
        src = MockSensor(devices=["d1"], metrics=["temperature"],
                         base={"temperature": 40.0}, store=store, engine=eng)
        # 手动喂高温
        r = src.feed("d1", "temperature", 95.0)
        assert r["ingest"] == 1
        assert r["alerts"] == 1
        assert r["tickets"] == 1
        assert store.tickets("open")
        assert store.latest("d1", "temperature")["value"] == 95.0


# ═══════════════════════════ 5. AI 问数 MonitorAsk ═══════════════════════════
class TestMonitorAsk:
    def _setup(self, store, engine):
        store.set_rule("d1", "temperature", ">", 80.0, level="high")
        store.set_rule("d2", "temperature", ">", 80.0, level="high")
        raised = engine.evaluate_point("d1", "temperature", 90.0)
        engine.alert_to_ticket(raised[0])

    def test_ask_high_temp_device(self, store, engine):
        self._setup(store, engine)
        ask = MonitorAsk(store, engine)
        r = ask.ask("哪台设备温度过高")
        assert r["mode"] == "metric"
        assert "d1" in r["answer"]

    def test_ask_recent_alerts(self, store, engine):
        self._setup(store, engine)
        ask = MonitorAsk(store, engine)
        r = ask.ask("最近有哪些告警")
        assert r["mode"] == "alert"
        assert r["count"] >= 1

    def test_ask_max_temp(self, store, engine):
        self._setup(store, engine)
        store.record("d2", "temperature", 95.0)  # d2 更高
        ask = MonitorAsk(store, engine)
        r = ask.ask("温度最高的设备")
        assert r["device"]["device_id"] == "d2"

    def test_ask_open_tickets(self, store, engine):
        self._setup(store, engine)
        ask = MonitorAsk(store, engine)
        r = ask.ask("有哪些待处理工单")
        assert r["mode"] == "ticket"
        assert r["count"] == 1

    def test_ask_unknown_returns_miss(self, store, engine):
        ask = MonitorAsk(store, engine)
        r = ask.ask("你好")
        assert r["mode"] == "miss"
