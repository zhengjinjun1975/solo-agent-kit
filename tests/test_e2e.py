# -*- coding: utf-8 -*-
"""solo-agent-kit 端到端测试套件（pytest）。

逐项端到端：启动测试 web 服务 → 真实 API → 验证输出。
覆盖：对话路由/写作/代码/决策/清洗/分析/本体/技能/部署/配置/FDE(监控日志浏览)。

跑法：python -m pytest tests/test_e2e.py -v
"""
import json
import os
import socket
import subprocess
import sys
import time
import threading
import urllib.request
import urllib.error

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "examples", "data")
PORT = 8818


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
    """启动测试 web 服务。"""
    port = _free_port()
    # 隔离 survey 落盘到临时目录，避免端到端测试污染 ~/.solo/surveys
    import tempfile
    survey_dir = tempfile.mkdtemp(prefix="solo_e2e_survey_")
    _env = dict(os.environ, SOLO_SURVEY_DIR=survey_dir)
    proc = subprocess.Popen(
        [sys.executable, os.path.join(REPO, "solo", "web_server.py"), "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_env)
    base = f"http://127.0.0.1:{port}"
    # 等待就绪
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


def api(server, path, method="GET", body=None, t=40):
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


# ---- 对话路由 ----
def test_chat_clean_intent(server):
    _, r = api(server, "/api/agent", "POST", {"task": "清洗 factory_sensor.csv 并去重"})
    assert r.get("intent") == "clean"


def test_chat_stats_intent(server):
    _, r = api(server, "/api/agent", "POST", {"task": "分析 temp_c 趋势"})
    assert r.get("intent") == "stats"


def test_chat_ontology_intent(server):
    _, r = api(server, "/api/agent", "POST", {"task": "用 factory_equipment.csv 建本体"})
    assert r.get("intent") == "ontology"


# ---- 写作 ----
def test_writing_scan(server):
    _, r = api(server, "/api/writing", "POST", {"text": "这是一个测试通过赋能闭环"})
    assert r.get("issues") is not None


def test_writing_styles(server):
    _, r = api(server, "/api/writing", "POST", {"action": "styles"})
    assert len(r.get("styles", {})) >= 4


def test_writing_rewrite(server):
    _, r = api(server, "/api/writing", "POST", {"action": "rewrite", "text": "测试", "style": "tweet"})
    assert r.get("style") == "tweet"


# ---- 代码 ----
def test_code_overview(server):
    _, r = api(server, "/api/code-overview?dir=solo")
    assert r.get("indexed", 0) > 0


def test_code_review(server):
    _, r = api(server, "/api/code-review", "POST", {"dir": "solo", "file": "solo/cli.py"})
    assert r.get("file") == "cli.py"


# ---- 决策 ----
def test_decisions(server):
    _, r = api(server, "/api/decisions", "POST", {"csvs": [
        os.path.join(DATA, "decisions", "inventory.csv"),
        os.path.join(DATA, "decisions", "sales.csv")]})
    assert r.get("total", 0) >= 0


# ---- 需求→验收（survey 打通入口）----
def test_survey_outline(server):
    from urllib.parse import quote
    _, r = api(server, "/api/survey/outline?industry=" + quote("阀门制造"))
    assert r.get("kb") == "valve"
    assert isinstance(r.get("questions"), list)


def test_survey_structure_and_acceptance(server):
    name = "e2e_survey_p1_%d" % int(time.time())  # 唯一名，防跨次运行状态污染(~/.solo/surveys)
    _, r = api(server, "/api/survey", "POST", {"action": "structure", "name": name,
                                               "story": "库存盘点耗时",
                                               "acceptance": ["对账成功率≥99%"]})
    assert r.get("id") == "R-001"
    _, r = api(server, "/api/survey", "POST", {"action": "acceptance", "name": name})
    assert r.get("count") == 1
    assert r.get("check", {}).get("ok") is True


# ---- 数据清洗 ----
def test_clean(server):
    _, r = api(server, "/api/clean", "POST", {"csv": os.path.join(DATA, "factory_sensor.csv")})
    assert r.get("output", 0) > 0


# ---- 数据分析 ----
def test_stats(server):
    _, r = api(server, "/api/stats", "POST", {"csv": os.path.join(DATA, "factory_sensor.csv"), "col": "temp_c"})
    assert r.get("describe", {}).get("mean") is not None


def test_datasource_columns(server):
    _, r = api(server, "/api/datasource-columns", "POST", {"csv": os.path.join(DATA, "factory_sensor.csv")})
    assert len(r.get("columns", [])) > 0


# ---- 本体建模 ----
def test_ontology_multi(server):
    _, r = api(server, "/api/ontology-multi", "POST", {"csvs": [
        os.path.join(DATA, "factory_equipment.csv"),
        os.path.join(DATA, "factory_sensor.csv")]})
    assert len(r.get("entities", [])) >= 2


# ---- 技能 ----
def test_skills(server):
    _, r = api(server, "/api/skills")
    assert r.get("skills") is not None


# ---- 部署/配置 ----
def test_deploy(server):
    _, r = api(server, "/api/deploy")
    # 部署检查应返回步骤（Ollama 是否运行不影响结构）
    assert len(r.get("steps", [])) >= 4


def test_config(server):
    status, _ = api(server, "/api/config")
    assert status == 200


# ---- FDE 能力 ----
def test_monitor(server):
    _, r = api(server, "/api/monitor")
    # psutil 缺失时降级（percent 可为 None），但结构必须完整
    assert "cpu" in r and "memory" in r and "processes" in r


def test_logs(server):
    _, r = api(server, "/api/logs")
    assert r.get("logs") is not None


def test_browse(server):
    _, r = api(server, "/api/browse?dir=examples%2Fdata")
    assert len(r.get("files", [])) > 0
