# -*- coding: utf-8 -*-
"""monitor 设备监测 web 化 + 防断链端到端测试。

用户要求「一切归结到 web + 防断链」。本套件启动真实 web 服务（隔离数据目录
SOLO_MONITOR_DIR → 临时目录，不污染 ~/.solo/monitor），验证设备监测全链路
在 web 可操作、无断链：

    ingest → 指标存储 → 告警引擎 → 工单状态机 → AI问数

覆盖 web 端点：
    GET  /api/monitor/metrics     指标看板快照
    GET  /api/monitor/alerts      告警列表
    GET  /api/monitor/tickets     工单列表
    POST /api/monitor/rule        设置告警规则
    POST /api/monitor/ingest      接入指标（全链路）
    POST /api/monitor/ticket-state 推进工单状态机
    POST /api/monitor/ask         AI 问数
    POST /api/monitor/demo        一键端到端演示

跑法：python -m pytest tests/test_monitor_web.py -v
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _opener():
    """返回绕过系统代理的 opener。

    Windows 会把系统/注册表代理(如 127.0.0.1:xxxx)注入 urllib，
    导致本机测试 web 服务的 localhost 请求被代理劫持而 ConnectionRefused。
    测试只访问 127.0.0.1，禁用代理保证与开发者本机代理设置解耦。
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


@pytest.fixture(scope="module")
def server():
    """启动隔离数据目录的测试 web 服务（SOLO_MONITOR_DIR → 临时目录）。"""
    port = _free_port()
    mon_dir = tempfile.mkdtemp(prefix="monitor_web_")
    _env = dict(os.environ, SOLO_MONITOR_DIR=mon_dir)
    proc = subprocess.Popen(
        [sys.executable, os.path.join(REPO, "solo", "web_server.py"), "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(20):
        try:
            _opener().open(base + "/", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def api(server, path, method="GET", body=None, t=20):
    try:
        if method == "POST":
            req = urllib.request.Request(server + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(server + path)
        with _opener().open(req, timeout=t) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"_error": str(e)[:100]}


# ═══════════════════════ 防断链：全链路 web 可操作 ═══════════════════════
class TestMonitorWebFullChain:
    def test_ingest_to_ticket_to_ask_no_break(self, server):
        # 1) 设规则（阈值 >80，触发自动建工单）
        st, r = api(server, "/api/monitor/rule", "POST",
                    {"device_id": "d_web", "metric": "temperature", "op": ">",
                     "threshold": 80, "level": "high"})
        assert st == 200 and r.get("ok") is True

        # 2) 接入高温 → ingest 全链路返回新增告警/工单
        st, r = api(server, "/api/monitor/ingest", "POST",
                    {"device_id": "d_web", "metric": "temperature", "value": 95})
        assert st == 200
        assert r["alerts"] == 1, "接入高温应触发 1 条告警"
        assert r["tickets"] == 1, "告警应自动建 1 张工单"
        assert r["latest"]["value"] == 95.0, "指标已写入存储"

        # 3) 指标看板快照：能看到 d_web + 触发中告警
        st, r = api(server, "/api/monitor/metrics")
        assert st == 200
        assert any(d["device_id"] == "d_web" for d in r["devices"]), "看板含新设备"
        assert r["alerts"]["firing"] >= 1, "看板统计到触发中告警"
        assert r["tickets"]["open"] >= 1, "看板统计到开放工单"

        # 4) 告警列表：含 d_web 触发中告警
        st, r = api(server, "/api/monitor/alerts")
        assert st == 200 and r["count"] >= 1
        assert any(a["device_id"] == "d_web" and a["state"] == "firing" for a in r["alerts"])

        # 5) 工单列表：含开放工单
        st, r = api(server, "/api/monitor/tickets?state=open")
        assert st == 200 and r["count"] >= 1
        ticket_id = r["tickets"][0]["id"]
        assert r["tickets"][0]["device_id"] == "d_web"

        # 6) 工单状态机：open → in_progress → done
        st, r = api(server, "/api/monitor/ticket-state", "POST",
                    {"ticket_id": ticket_id, "target": "in_progress", "note": "已派工"})
        assert st == 200 and r["state"] == "in_progress"
        st, r = api(server, "/api/monitor/ticket-state", "POST",
                    {"ticket_id": ticket_id, "target": "done", "note": "处理完成"})
        assert st == 200 and r["state"] == "done" and r["done_at"]

        # 7) 非法流转被拒（done 不能回 open）
        st, r = api(server, "/api/monitor/ticket-state", "POST",
                    {"ticket_id": ticket_id, "target": "open"})
        assert st == 400 and "error" in r

        # 8) AI 问数：查到 d_web 温度过高（先查库再回答，无幻觉）
        st, r = api(server, "/api/monitor/ask", "POST",
                    {"question": "哪台设备温度过高"})
        assert st == 200 and r["mode"] == "metric"
        assert "d_web" in r["answer"], f"问数应答出设备, 得: {r['answer']}"

    def test_ask_alert_and_ticket_modes(self, server):
        st, r = api(server, "/api/monitor/ask", "POST", {"question": "最近有哪些告警"})
        assert st == 200 and r["mode"] == "alert" and r["count"] >= 1
        st, r = api(server, "/api/monitor/ask", "POST", {"question": "有哪些待处理工单"})
        assert st == 200 and r["mode"] == "ticket"

    def test_missing_params_rejected(self, server):
        # ingest 缺参 → 400
        st, r = api(server, "/api/monitor/ingest", "POST", {"device_id": "d_x"})
        assert st == 400 and "error" in r
        # ask 缺 question → 400
        st, r = api(server, "/api/monitor/ask", "POST", {})
        assert st == 400 and "error" in r
        # rule 缺 threshold → 400
        st, r = api(server, "/api/monitor/rule", "POST",
                    {"device_id": "d_x", "metric": "power"})
        assert st == 400 and "error" in r

    def test_one_click_demo_populates_chain(self, server):
        # 一键端到端演示：模拟数据→告警→工单→AI问数，全链路可跑通
        st, r = api(server, "/api/monitor/demo", "POST", {"rounds": 8})
        assert st == 200
        assert r["metrics"] > 0 and r["total_alerts"] > 0 and r["tickets"] > 0
        assert "设备" in r["q_high_temp"] or "d1" in r["q_high_temp"] or "温度" in r["q_high_temp"]
        # 演示后看板可见数据
        st, snap = api(server, "/api/monitor/metrics")
        assert snap["device_count"] > 0 and snap["metric_count"] > 0

    def test_get_routes_respond(self, server):
        # 三个只读 GET 端点均 200 且结构完整（空库也不断链）
        st, r = api(server, "/api/monitor/alerts")
        assert st == 200 and "alerts" in r and "count" in r
        st, r = api(server, "/api/monitor/tickets")
        assert st == 200 and "tickets" in r and "count" in r
        st, r = api(server, "/api/monitor/metrics")
        assert st == 200 and "devices" in r and "alerts" in r and "tickets" in r
