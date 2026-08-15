# -*- coding: utf-8 -*-
"""solo 各项浅→深 P0 测试：监测协议直采/规则链、写作证据账本、记忆写入决策层、
任务工单状态机审计、本体语义贯通。

每项用真实数据验证（非空壳），覆盖 P0 深化的确定性行为。
跑法：python -m pytest tests/test_deep_p0.py -v
"""
import os
import socket
import tempfile
import threading

import pytest

sys_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path not in os.sys.path:
    os.sys.path.insert(0, sys_path)

from solo.factory import protocols as proto
from solo.factory import monitor as mon
from solo.factory import evidence as ev
from solo.memory import Memory
from solo.task import Task
from solo.factory.ontology import semantic as sem


@pytest.fixture()
def mon_dir():
    d = tempfile.mkdtemp(prefix="deep_mon_")
    old = os.environ.get("SOLO_MONITOR_DIR")
    os.environ["SOLO_MONITOR_DIR"] = d
    yield d
    if old:
        os.environ["SOLO_MONITOR_DIR"] = old


# ═══════════════════════ 1. 监测 P0 协议直采（真实设备接入抽象）═══════════════════════
class TestProtocolDirectCollect:
    def test_protocol_registry_lists_builtin_and_optional(self):
        ps = proto.protocols()
        assert ps["tcp"]["builtin"] is True
        assert ps["http"]["builtin"] is True
        assert ps["mqtt"]["builtin"] is False
        assert ps["modbus"]["builtin"] is False
        assert ps["opcua"]["builtin"] is False

    def test_tcp_real_server_collect(self, mon_dir):
        """真实 TCP 服务端推一条 JSON → 协议直采归一为统一指标点。"""
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def serve():
            c, _ = srv.accept()
            c.sendall(b'{"device_id":"d_real","metric":"temperature","value":45.2}')
            c.close()
            srv.close()

        threading.Thread(target=serve, daemon=True).start()
        src = proto.create_source({"protocol": "tcp", "host": "127.0.0.1",
                                   "port": port})
        pts = src.collect()
        src.close()
        assert pts and pts[0]["device_id"] == "d_real"
        assert pts[0]["metric"] == "temperature"
        assert pts[0]["value"] == 45.2

    def test_http_ingest_gateway_full_chain(self, mon_dir):
        """HTTP webhook 直采网关：真实设备 POST → 存储 → 告警 → 工单 全链路。"""
        store = mon.MetricStore(mon_dir)
        store.set_rule("d_http", "temperature", ">", 80, level="high")
        g = proto.HttpIngestGateway(store=store, engine=mon.AlertEngine(store),
                                    auto_ticket=True)
        r = g.ingest({"device_id": "d_http", "metric": "temperature", "value": 95})
        assert r["ingested"] == 1
        assert r["alerts"] == 1, "HTTP 直采应触发告警"
        assert r["tickets"] == 1, "HTTP 直采应自动建工单"
        assert store.latest("d_http", "temperature")["value"] == 95.0

    def test_http_ingest_multi_device_map(self, mon_dir):
        """HTTP 直采多设备映射：{设备:{指标:值}} 批量归一。"""
        g = proto.HttpIngestGateway(store=mon.MetricStore(mon_dir))
        r = g.ingest({"d1": {"temperature": 60, "power": 30},
                      "d2": {"vibration": 3.5}})
        assert r["ingested"] == 3
        assert len(g.store.devices()) == 2

    def test_invalid_value_raises(self, mon_dir):
        """非法指标值抛 ProtocolError（防脏数据入库）。"""
        with pytest.raises(proto.ProtocolError):
            proto.HttpPushSource({})._point("d1", "temp", "abc")


# ═══════════════════════ 1b. 监测 P1 规则链（JSON 配置告警）═══════════════════════
class TestRuleChain:
    def test_chain_threshold_alert(self, mon_dir):
        rc = mon.RuleChain(mon.MetricStore(mon_dir))
        rc.add({"id": "r1", "when": {"device": "d1", "metric": "temperature",
                                     "cond": ">", "threshold": 80},
                "action": "alert", "level": "high"})
        fired = rc.evaluate_point("d1", "temperature", 90)
        assert len(fired) == 1
        assert fired[0]["action"] == "alert"
        assert fired[0]["chain"] is True
        assert rc.list()[0]["id"] == "r1"

    def test_chain_ignores_other_device(self, mon_dir):
        rc = mon.RuleChain(mon.MetricStore(mon_dir))
        rc.add({"id": "r1", "when": {"device": "d1", "metric": "temperature",
                                     "cond": ">", "threshold": 80},
                "action": "alert"})
        assert rc.evaluate_point("d2", "temperature", 90) == []

    def test_chain_combo_and(self, mon_dir):
        """组合条件 AND：两指标同时满足才触发。"""
        store = mon.MetricStore(mon_dir)
        store.record("d1", "power", 4.0)
        rc = mon.RuleChain(store)
        rc.add({"id": "r2", "when": {"metric": "power", "cond": "<", "threshold": 5},
                "combos": [{"metric": "power", "op2": ">", "threshold": 3}],
                "action": "ticket", "level": "medium"})
        fired = rc.evaluate_point("d1", "power", 4.0)
        assert fired and fired[0]["action"] == "ticket"
        assert store.tickets("open"), "组合条件触发应建工单"

    def test_chain_combo_or(self, mon_dir):
        """组合条件 OR：任一满足即触发。"""
        store = mon.MetricStore(mon_dir)
        store.record("d2", "power", 50)
        store.record("d2", "temperature", 10)
        rc = mon.RuleChain(store)
        rc.add({"id": "r3", "when": {"metric": "power", "cond": ">", "threshold": 40},
                "combos": [{"metric": "power", "op2": ">", "threshold": 40},
                           {"op": "OR", "metric": "temperature", "op2": ">", "threshold": 90}],
                "action": "alert"})
        assert len(rc.evaluate_point("d2", "power", 50)) == 1  # power 分支真

    def test_chain_idempotent(self, mon_dir):
        """幂等：同规则同设备 firing 不重复触发。"""
        rc = mon.RuleChain(mon.MetricStore(mon_dir))
        rc.add({"id": "r1", "when": {"metric": "temperature", "cond": ">",
                                     "threshold": 80}, "action": "alert"})
        assert len(rc.evaluate_point("d1", "temperature", 90)) == 1
        assert rc.evaluate_point("d1", "temperature", 95) == []
        assert rc.evaluate_point("d1", "temperature", 96) == []


# ═══════════════════════ 2. 写作 P0 证据账本 + 事实核查 ═══════════════════════
class TestEvidenceFactCheck:
    def test_ledger_extracts_claims(self):
        ledger = ev.build_ledger("设备温度达到 92，功率为 30，内存占用 85%")
        types = [c["type"] for c in ledger]
        assert "number" in types
        assert "percent" in types

    def test_fact_check_supported(self):
        rows = [{"temperature": 90, "power": 30}, {"temperature": 95, "power": 25}]
        res = ev.fact_check("设备温度达到 92，功率为 30", rows)
        assert res["summary"]["supported"] >= 1
        assert res["summary"]["contradicted"] == 0

    def test_fact_check_contradicted(self):
        rows = [{"temperature": 90, "power": 30}]
        res = ev.fact_check("功率为 100", rows)  # 源 power 最新 30，矛盾
        assert res["summary"]["contradicted"] >= 1

    def test_fact_check_no_source_unsupported(self):
        res = ev.fact_check("温度达到 92", [])
        assert all(c["status"] == "unsupported" for c in res["ledger"])
        assert res["summary"]["unsupported"] == res["summary"]["total"]

    def test_claim_has_trace_id(self):
        ledger = ev.build_ledger("温度达到 92")
        assert all(c.get("trace_id") for c in ledger)


# ═══════════════════════ 3. 记忆 P0 写入决策层 ═══════════════════════
class TestMemoryWriteDecision:
    @pytest.fixture()
    def mem(self):
        return Memory(tempfile.mkdtemp(prefix="deep_mem_"))

    def test_add_new(self, mem):
        r = mem.write("设备 d1 温度 90 度")
        assert r["action"] == "ADD"
        assert len(mem._load(mem._facts_path, [])) == 1

    def test_skip_exact_duplicate(self, mem):
        mem.write("设备 d1 温度 90 度")
        r = mem.write("设备 d1 温度 90 度")
        assert r["action"] == "SKIP"
        assert len(mem._load(mem._facts_path, [])) == 1, "完全重复不堆积"

    def test_update_variant(self, mem):
        mem.write("设备 d1 温度 90 度")
        r = mem.write("设备d1温度90", threshold=0.3)
        assert r["action"] == "UPDATE"
        assert len(mem._load(mem._facts_path, [])) == 1, "同主题更新不新增"

    def test_update_fact_explicit(self, mem):
        mem.write("设备 d1 温度 90 度")
        r = mem.update_fact("设备 d1 温度 90 度", "设备 d1 温度 95 度")
        assert r["ok"] is True and r["action"] == "UPDATE"
        assert r["fact"]["text"] == "设备 d1 温度 95 度"
        assert "history" in r["fact"]

    def test_delete_fact(self, mem):
        mem.write("设备 d1 温度 90 度")
        r = mem.delete_fact(text="设备 d1 温度 90 度")
        assert r["ok"] is True and r["action"] == "DELETE"
        assert len(mem._load(mem._facts_path, [])) == 0


# ═══════════════════════ 4. 任务 P0 工单状态机 + 审计 ═══════════════════════
class TestTaskStateMachineAudit:
    @pytest.fixture()
    def t(self):
        return Task(tempfile.mkdtemp(prefix="deep_task_"))

    def test_full_lifecycle_audit(self, t):
        iss = t.new_issue("部署失败")
        # open → in_progress → diagnosed → resolved → closed
        assert t.transition(iss["id"], "in_progress", "user", "已派工")["state"] == "in_progress"
        assert t.diagnose(iss["id"], "端口占用")["state"] == "diagnosed"
        assert t.resolve_issue(iss["id"], "释放端口")["state"] == "resolved"
        assert t.transition(iss["id"], "closed", "user", "验收通过")["state"] == "closed"
        aud = t.issue_audit(iss["id"])
        assert aud["state"] == "closed"
        # 审计轨迹：创建 + 4 步流转
        assert len(aud["audit"]) >= 5
        # 从 open 到 closed，每一步都记录 from/to
        seq = [(a["from"], a["to"]) for a in aud["audit"]]
        assert ("open", "in_progress") in seq
        assert ("resolved", "closed") in seq
        assert all(a.get("actor") for a in aud["audit"])

    def test_illegal_transition_rejected(self, t):
        iss = t.new_issue("数据库连接失败")
        r = t.transition(iss["id"], "closed")  # open 不能直接 closed? 实际 open→closed 合法
        # open → closed 合法；非法: closed → open
        assert r["state"] == "closed"
        r2 = t.transition(iss["id"], "open")
        assert "error" in r2

    def test_audit_actor_recorded(self, t):
        iss = t.new_issue("性能慢")
        t.transition(iss["id"], "in_progress", "monitor", "自动派工")
        aud = t.issue_audit(iss["id"])
        assert any(a["actor"] == "monitor" for a in aud["audit"])

    def test_new_issue_inits_audit(self, t):
        iss = t.new_issue("告警触发")
        aud = t.issue_audit(iss["id"])
        assert aud["audit"][0]["to"] == "open"
        assert aud["audit"][0]["actor"] == "system"


# ═══════════════════════ 5. 本体 P0 语义贯通 ═══════════════════════
class TestOntologySemantic:
    def test_semantic_role_measure(self):
        assert sem.semantic_role("temperature")["role"] == "measure"
        assert sem.semantic_role("cpu_percent")["role"] == "measure"

    def test_semantic_role_identifier_reference(self):
        assert sem.semantic_role("id")["role"] == "identifier"
        assert sem.semantic_role("device_id")["role"] == "reference"

    def test_consistency_all_ok(self):
        r = sem.semantic_consistency(["device_id", "temperature", "power"])
        assert r["all_ok"] is True

    def test_consistency_flags_misnamed(self):
        # "温度类型" 含 measure 词被分类 category → 错位
        r = sem.semantic_consistency(["温度类型"])
        assert r["all_ok"] is False

    def test_link_entities_multi_table(self):
        data = {
            "factory_device": [{"id": "D1", "temperature": 90, "device_type": "pump",
                                "line_id": "L1"}],
            "factory_line": [{"id": "L1", "name": "装配线"}],
        }
        r = sem.link_entities(data)
        assert "Device" in r["entities"]
        assert r["edges"] >= 1, "多表关联应建实例图边"
        assert "roles" in r and "Device" in r["roles"]

    def test_semantic_bridge_blocks(self):
        b = sem.semantic_bridge({"monitor": ["cpu_percent", "device_id"],
                                 "task": ["severity", "device_id"]})
        assert b["blocks"]["monitor"]["consistency"]["all_ok"]
        assert "Device" in b["bridge"]["entities"]
