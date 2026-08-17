# -*- coding: utf-8 -*-
"""web_server.py — solo-agent-kit 极简 Web 后端（标准库，零依赖）。

前端 web/index.html 的 API 后端。暴露：
    GET  /api/capabilities      能力清单（双套件）
    GET  /api/config            读 provider.yaml 配置（脱敏）
    POST /api/config            写 provider.yaml 配置
    POST /api/run               执行任务（走 agent 循环）
    GET  /api/memory            记忆概览
    GET  /api/skills            技能清单
    GET  /api/stats?csv=&col=   工厂数据分析

启动：python solo/web_server.py [--port 8743]
前端：http://localhost:8743

拆分说明：端点处理方法（原 _handle_api_post 圈复杂度105 / _handle_api_get 58 的
每个分支）已拆到 solo/web_routes.py 的 _GetRoutesMixin/_PostRoutesMixin。本文件保持
薄壳：HTTP 基座 + 路由注册表(_GET_ROUTES/_POST_ROUTES) + 查表分发(_dispatch)。
业务逻辑仍下沉 solo/app.py 与 solo/web_api.py。
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import web_api as api  # 业务逻辑层（辅助函数/数据源处理）
from solo import app as app_mod  # 统一服务门面（业务单一事实来源）
from solo.web_routes import _GetRoutesMixin, _PostRoutesMixin

PORT = 8743

# 能力清单（唯一来源 = app.CAPABILITIES）
CAPABILITIES = app_mod.CAPABILITIES


class SoloHandler(_GetRoutesMixin, _PostRoutesMixin, BaseHTTPRequestHandler):
    """HTTP 后端：继承端点 mixin + 标准库 BaseHTTPRequestHandler。

    路由注册表把路径映射到端点方法名（定义于 web_routes mixin），
    _dispatch 查表分发，避免巨型 if/elif。
    """
    # 路由注册表：路径 → 处理方法名。
    _GET_ROUTES = {
        "/api/capabilities": "_get_capabilities",
        "/api/config": "_get_config",
        "/api/memory": "_get_memory",
        "/api/skills": "_get_skills",
        "/api/memory-search": "_get_memory_search",
        "/api/code-overview": "_get_code_overview",
        "/api/stats": "_get_stats",
        "/api/setup": "_get_setup",
        "/api/task": "_get_task",
        "/api/survey/outline": "_get_survey_outline",
        "/api/deploy": "_get_deploy",
        "/api/monitor": "_get_monitor",
        "/api/monitor/devices": "_get_monitor_devices",
        "/api/monitor/metrics": "_get_monitor_metrics",
        "/api/monitor/alerts": "_get_monitor_alerts",
        "/api/monitor/tickets": "_get_monitor_tickets",
        "/api/site/devices": "_get_site_devices",
        "/api/data/fetch": "_get_data_fetch",
        "/api/charts/spc": "_get_charts_spc",
        "/api/logs": "_get_logs",
        "/api/config-test": "_get_config_test",
        "/api/datasource": "_get_datasource",
        "/api/browse": "_get_browse",
        "/api/db-connect": "_get_db_connect",
        "/api/db-preview": "_get_db_preview",
        "/api/industry": "_get_industry",
        "/api/memory/optmem-search": "_get_optmem_search",
        "/api/monitor/protocols": "_get_monitor_protocols",
        "/api/monitor/chain": "_get_monitor_chain",
        "/api/writing/evidence": "_get_writing_evidence",
        "/api/task/audit": "_get_task_audit",
        "/api/ontology/semantic": "_get_ontology_semantic",
    }
    _POST_ROUTES = {
        "/api/config": "_post_config",
        "/api/stats": "_post_stats",
        "/api/remote": "_post_remote",
        "/api/rdbms-connect": "_post_rdbms_connect",
        "/api/task": "_post_task",
        "/api/run": "_post_run",
        "/api/agent": "_post_agent",
        "/api/toggle": "_post_toggle",
        "/api/clean": "_post_clean",
        "/api/report": "_post_report",
        "/api/export": "_post_export",
        "/api/datasource-columns": "_post_datasource_columns",
        "/api/ontology": "_post_ontology",
        "/api/ontology-multi": "_post_ontology_multi",
        "/api/decisions": "_post_decisions",
        "/api/memory-add": "_post_memory_add",
        "/api/survey": "_post_survey",
        "/api/skill-add": "_post_skill_add",
        "/api/writing": "_post_writing",
        "/api/code-review": "_post_code_review",
        "/api/code-review-file": "_post_code_review_file",
        "/api/gen": "_post_gen",
        "/api/onto/nt": "_post_onto_nt",
        "/api/onto/answer": "_post_onto_answer",
        "/api/onto/search": "_post_onto_search",
        "/api/delivery": "_post_delivery",
        "/api/industry": "_post_industry",
        "/api/memory/optmem-note": "_post_optmem_note",
        "/api/monitor/ingest": "_post_monitor_ingest",
        "/api/monitor/ask": "_post_monitor_ask",
        "/api/monitor/rule": "_post_monitor_rule",
        "/api/monitor/ticket-state": "_post_monitor_ticket_state",
        "/api/monitor/demo": "_post_monitor_demo",
        "/api/monitor/protocol/http": "_post_monitor_protocol_http",
        "/api/monitor/protocol/probe": "_post_monitor_protocol_probe",
        "/api/monitor/chain": "_post_monitor_chain",
        "/api/site/devices": "_post_site_device",
        "/api/memory/write": "_post_memory_write",
        "/api/memory/update": "_post_memory_update",
        "/api/memory/delete": "_post_memory_delete",
        "/api/memory/auto-sediment": "_post_memory_auto_sediment",
        "/api/skill/auto-generate": "_post_skill_auto_generate",
        "/api/ontology/semantic": "_post_onto_semantic",
    }

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # CORS 收窄到本地（默认本地部署，不暴露 *）
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:" + str(self.server.server_port) if hasattr(self.server, "server_port") else "null")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path):
        """服务前端静态文件。"""
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
        if path in ("/", "/index.html"):
            path = "index.html"
        else:
            path = path.lstrip("/")
        full = os.path.normpath(os.path.join(web_dir, path))
        # 路径穿越防护: 用 commonpath 检查 full 确实在 web_dir 内(含分隔符边界, 防 web_evil 同前缀绕过)
        web_dir_norm = os.path.normpath(web_dir)
        try:
            inside = os.path.commonpath([full, web_dir_norm]) == web_dir_norm
        except ValueError:
            inside = False
        if not inside or not os.path.exists(full):
            self._json({"error": "not found"}, 404)
            return
        ext = os.path.splitext(full)[1]
        ctype = {"": "text/html", ".html": "text/html", ".css": "text/css",
                 ".js": "application/javascript"}.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if n == 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            # 容忍非 UTF-8（如 Windows curl 发送的 GBK）
            return json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            try:
                self._dispatch(self._GET_ROUTES, path,
                               lambda: urllib.parse.parse_qs(parsed.query))
            except Exception as e:
                self._handle_error(e)
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._read_body()
        try:
            self._dispatch(self._POST_ROUTES, path, body)
        except Exception as e:
            self._handle_error(e)

    def _dispatch(self, routes, path, payload):
        """查表分发：routes[path] → 处理方法；未命中 → 404。

        payload 语义因路由而异：GET 传 qs lambda（懒取 query），POST 传已解析的 body dict。
        """
        handler_name = routes.get(path)
        if handler_name is None:
            self._json({"error": "unknown api"}, 404)
            return
        getattr(self, handler_name)(payload)

    def _handle_error(self, e: Exception):
        """P0-3: 统一错误契约——ApiError 返回其 code/msg，其他记日志返回通用 500。"""
        from solo.base import ApiError, get_logger
        if isinstance(e, ApiError):
            self._json(e.to_dict(), e.code)
            return
        get_logger("solo.web").error("API 未捕获异常: %s", e, exc_info=True)
        self._json({"error": "内部错误，请查看日志", "code": 500}, 500)

    # ---- 数据分析通用应答（GET/POST 端点共用）----
    def _reply_stats(self, rows, col):
        if not rows:
            self._json({"error": "数据源无效或为空"}, 400)
            return
        res = app_mod.data_stats(rows, col)
        if "error" in res:
            self._json({"error": res["error"]}, 400)
            return
        self._json(res)

    def log_message(self, fmt, *args):
        # P0-2: 记录请求日志（不再静默 pass）
        from solo.base import get_logger
        get_logger("solo.web").info("%s - %s", self.address_string(), fmt % args)


def main():
    ap = argparse.ArgumentParser(description="solo-agent-kit Web 后端")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    # P1-4: ThreadingHTTPServer 支持并发（慢请求不阻塞其他 API）
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer((args.host, args.port), SoloHandler)
    print(f"solo web 后端已启动: http://{args.host}:{args.port}  (Ctrl+C 停止)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.server_close()


if __name__ == "__main__":
    main()
