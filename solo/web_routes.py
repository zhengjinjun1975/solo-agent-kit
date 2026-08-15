# -*- coding: utf-8 -*-
"""web_routes.py — Web 端点处理方法（按 GET/POST 拆成两个 mixin）。

从 web_server.py 拆出：原 _handle_api_post(圈复杂度105)/_handle_api_get(58) 的
每个分支对应一个端点方法。web_server.SoloHandler 通过继承组合这两个 mixin，
_GET_ROUTES/_POST_ROUTES 注册表在 web_server 中做查表分发。

每个方法只服务一个 API 路径，单一职责；业务逻辑仍下沉 app/web_api/factory。
"""
from __future__ import annotations

import json
import os

from solo import provider as provider_mod
from solo import memory as memory_mod
from solo import skill as skill_mod
from solo import web_api as api
from solo import app as app_mod

# 能力清单（唯一来源 = app.CAPABILITIES），供 _post_toggle 切换 enabled 状态
CAPABILITIES = app_mod.CAPABILITIES


class _GetRoutesMixin:
    """GET 端点。qs 参数为 lambda（懒取 parse_qs 结果）。"""

    def _get_capabilities(self, qs):
        self._json(app_mod.capabilities())

    def _get_config(self, qs):
        # 唯一脱敏配置视图（app.config_view）
        self._json(app_mod.config_view())

    def _get_memory(self, qs):
        m = memory_mod.Memory()
        facts = m._load(m._facts_path, [])
        self._json({"facts": len(facts), "profile": m.profile_text()})

    def _get_skills(self, qs):
        sk = skill_mod.Skill()
        self._json({"skills": sk.all_details()})

    def _get_memory_search(self, qs):
        m = memory_mod.Memory()
        q = qs().get("q", [""])[0]
        results = [{"text": f["text"], "ts": f.get("ts", "")} for f in m.search(q, top_k=5)]
        self._json({"query": q, "results": results})

    def _get_code_overview(self, qs):
        from solo import code as code_mod
        d = api.safe_path(qs().get("dir", [""])[0])
        cg = code_mod.CodeGraph()
        n = cg.index(d or "solo")
        self._json({"indexed": n, "symbols": len(cg.symbols), "overview": cg.overview()})

    def _get_stats(self, qs):
        # GET: csv+col 兼容；POST: 数据源对象（见 _post_stats）
        q = qs()
        csv_path = api.safe_path(q.get("csv", [""])[0])
        col = q.get("col", [None])[0]
        if not csv_path or not os.path.exists(csv_path):
            self._json({"error": "csv not found or outside project"}, 400)
            return
        from solo import data_connector as dc
        rows = dc.connect({"type": "csv", "path": csv_path})
        self._reply_stats(rows, col)

    def _get_setup(self, qs):
        self._json(app_mod.check_environment())

    def _get_task(self, qs):
        # 工单列表（GET：FDE 现场看未闭环问题）
        from solo.task import Task
        self._json({"issues": Task().list_issues()})

    def _get_survey_outline(self, qs):
        # 需求访谈提纲（survey 打通入口，行业数据驱动）
        self._json(app_mod.survey_outline(qs().get("industry", [None])[0]))

    def _get_deploy(self, qs):
        self._json(app_mod.deploy())

    def _get_monitor(self, qs):
        # 环境监控（FDE 现场资源看板）
        from solo.factory import ops as ops_mod
        self._json(ops_mod.system_stats())

    def _get_monitor_devices(self, qs):
        # 厂区设备批量巡检（复用 monitor_devices）
        try:
            from solo.factory import ops as ops_mod
            self._json({"devices": ops_mod.monitor_devices()})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _get_monitor_metrics(self, qs):
        # 设备监测：指标看板快照（设备+最新指标+告警/工单计数）
        from solo.factory import monitor as mon
        self._json(mon.monitor_snapshot())

    def _get_monitor_alerts(self, qs):
        # 设备监测：告警列表（?state=firing|recovered）
        from solo.factory import monitor as mon
        state = qs().get("state", [None])[0] or None
        store = mon.MetricStore()
        self._json({"alerts": store.alerts(state, limit=100),
                    "count": len(store.alerts(state))})

    def _get_monitor_tickets(self, qs):
        # 设备监测：工单列表（?state=open|in_progress|done）
        from solo.factory import monitor as mon
        state = qs().get("state", [None])[0] or None
        store = mon.MetricStore()
        self._json({"tickets": store.tickets(state),
                    "count": len(store.tickets(state))})

    def _get_monitor_protocols(self, qs):
        # 协议直采：可用协议清单（内置 TCP/HTTP，可选 MQTT/Modbus/OPC-UA）
        from solo.factory import protocols as proto
        self._json({"protocols": proto.protocols()})

    def _get_monitor_chain(self, qs):
        # 规则链：JSON 配置告警规则链清单（P1）
        from solo.factory import monitor as mon
        rc = mon.RuleChain()
        self._json({"rules": rc.list(), "count": len(rc.list())})

    def _get_writing_evidence(self, qs):
        # 写作证据账本+事实核查（P0）：需文本+数据源，POST 用；GET 返回能力说明
        from solo.factory import evidence as ev
        self._json({"capability": "POST /api/writing/evidence {text, source:{csv|db}, col_map}",
                    "report_format": {"ledger": [], "summary": {}}})

    def _get_task_audit(self, qs):
        # 任务：工单全生命周期操作审计（?id=xxx）
        from solo.task import Task
        tid = qs().get("id", [""])[0]
        if not tid:
            self._json({"error": "需 id 参数（工单号）"}, 400)
            return
        r = Task().issue_audit(tid)
        if "error" in r:
            self._json(r, 400)
            return
        self._json(r)

    def _get_ontology_semantic(self, qs):
        # 本体语义贯通：字段语义角色分类（?fields=温度,cpu_percent 或 ?block=monitor）
        from solo.factory.ontology import semantic as sem
        fields = [f.strip() for f in qs().get("fields", [""])[0].split(",") if f.strip()]
        block = qs().get("block", [None])[0]
        if block:
            blocks = {"monitor": ["device_id", "temperature", "power", "cpu_percent", "mem_percent"],
                      "task": ["device_id", "severity", "triage", "problem", "state"],
                      "memory": ["text", "tags", "ts", "updated"]}
            self._json(sem.semantic_bridge({block: blocks.get(block, [])}))
            return
        if not fields:
            self._json({"error": "需 fields 参数（逗号分隔字段名）"}, 400)
            return
        self._json({"fields": sem.cross_field_semantics(fields),
                    "consistency": sem.semantic_consistency(fields)})

    def _get_site_devices(self, qs):
        # 厂区设备台账
        try:
            from solo.factory.ops import Site
            s = Site()
            devs = s.devices() if callable(getattr(s, "devices", None)) else []
            cur = s.current_site if isinstance(s.current_site, str) else (s.current_site() if callable(s.current_site) else "")
            self._json({"devices": devs, "site": cur})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _get_data_fetch(self, qs):
        # 从厂区设备远程拉数据（data_connector 设备数据源）
        try:
            body = self._read_body()
            from solo import data_connector as dc
            src = {"type": "device", "device": body.get("device", ""),
                   "remote_path": body.get("remote_path", ""),
                   "path_type": body.get("path_type", "csv"),
                   "limit": body.get("limit", 10)}
            rows = dc.connect(src)
            self._json({"rows": rows[:body.get("limit", 10)], "count": len(rows)})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _get_charts_spc(self, qs):
        # SPC 控制图（visualize 插件）
        try:
            from urllib.parse import parse_qs, urlparse
            from solo.plugins import visualize as viz
            q = parse_qs(urlparse(self.path).query)
            values = [float(v) for v in q.get("values", [""])[0].split(",") if v]
            title = q.get("title", ["SPC 控制图"])[0]
            if not values:
                self._json({"error": "需要 values 参数(逗号分隔数值)"}, 400)
                return
            r = viz.spc_chart(values, title=title, filename="web_spc")
            self._json(r)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _get_logs(self, qs):
        # 日志诊断（FDE 排障第一动作）
        from solo.base import get_logs
        q = qs()
        qs_level = q.get("level", [None])[0]
        qs_limit = int(q.get("limit", ["100"])[0])
        self._json({"logs": get_logs(limit=qs_limit, level=qs_level)})

    def _get_config_test(self, qs):
        # 测试模型连接（本地 Ollama + 远端 API）
        import urllib.request
        p = provider_mod.Provider.from_file()
        out = {}
        # 测试本地
        if p.local:
            try:
                with urllib.request.urlopen(p.local.get("base_url", "http://127.0.0.1:11434").rstrip("/") + "/api/tags", timeout=3) as r:
                    models = [m.get("name", "") for m in json.load(r).get("models", [])]
                out["local"] = {"ok": True, "model": p.local.get("model"), "models": models[:5]}
            except Exception as e:
                out["local"] = {"ok": False, "error": str(e)[:60]}
        # 测试远端
        if p.remote:
            key = provider_mod.resolve_remote_key(p.remote)
            if not key:
                env_name = p.remote.get("api_key_env", "DEEPSEEK_API_KEY")
                out["remote"] = {"ok": False, "error": f"云端未配置 API key（设环境变量 {env_name}）"}
            else:
                out["remote"] = {"ok": True, "model": p.remote.get("model"),
                                 "api_key_env": p.remote.get("api_key_env", "DEEPSEEK_API_KEY")}
        self._json(out)

    def _get_datasource(self, qs):
        # 列出数据源信息：SQLite 表 / 检查 CSV
        from solo import data_connector as dc
        q = qs()
        db_path = q.get("db", [""])[0]
        csv_path = q.get("csv", [""])[0]
        result = {"sources": []}
        if db_path:
            result["sources"].append({"type": "sqlite", "path": db_path,
                                      "tables": dc.list_tables(api.safe_path(db_path))})
        if csv_path:
            sp = api.safe_path(csv_path)
            import os as _os
            result["sources"].append({"type": "csv", "path": sp,
                                      "exists": bool(sp and _os.path.exists(sp))})
        self._json(result)

    def _get_browse(self, qs):
        # 硬盘级文件遍历：盘符/目录导航（数据文件过滤）
        import os as _os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 默认根 = examples/data（示例数据直接可见），盘符/上级可导航到任意硬盘
        default_root = os.path.join(root, "examples", "data")
        dir_arg = qs().get("dir", [""])[0]
        if dir_arg:
            cur = dir_arg
            if not _os.path.isdir(cur):
                cur = default_root
        else:
            cur = default_root
        dirs, files = [], []
        try:
            for name in sorted(_os.listdir(cur)):
                full = _os.path.join(cur, name)
                if _os.path.isdir(full):
                    # 隐藏系统/敏感目录
                    if name not in ("$Recycle.Bin", "System Volume Information", "Recovery",
                                    "Windows", ".git", "__pycache__", "node_modules", ".venv", ".solo"):
                        dirs.append({"path": full, "name": name, "dir": True})
                else:
                    # 只列数据文件（JSON 是关系配置，不是数据表，排除）
                    if name.endswith((".csv", ".db", ".sqlite", ".xlsx")):
                        files.append({"path": full, "name": name, "dir": False})
        except Exception:
            pass
        # 盘符列表（Windows 根）——任何目录都返回，方便随时切硬盘
        parent = ""
        if _os.path.dirname(cur) != cur:
            parent = _os.path.dirname(cur)
        import string
        drives = [{"path": f"{d}:\\", "name": f"{d}:", "dir": True}
                  for d in string.ascii_uppercase if _os.path.exists(f"{d}:\\")]
        self._json({"dir": cur, "parent": parent, "dirs": dirs, "files": files, "drives": drives})

    def _get_db_connect(self, qs):
        # 数据库对接：连接→测试→列出表
        from solo import data_connector as dc
        body = self._read_body()
        db = api.safe_path(body.get("db", ""))
        if not db or not os.path.exists(db):
            self._json({"ok": False, "error": "数据库文件不存在"}, 400)
            return
        tables = dc.list_tables(db)
        if not tables:
            self._json({"ok": False, "error": "无法连接或库中无表"}, 400)
            return
        self._json({"ok": True, "db": db, "tables": tables})

    def _get_db_preview(self, qs):
        # 数据库表预览（前几行）
        from solo import data_connector as dc
        body = self._read_body()
        db = api.safe_path(body.get("db", ""))
        table = body.get("table", "")
        rows = dc.connect({"type": "sqlite", "path": db, "table": table})[:5]
        self._json({"rows": rows})

    def _get_industry(self, qs):
        # 行业联动状态（industry-list + industry-current）
        from solo.factory.industry import industries_list, get_current_industry, apply_industry
        self._json({"industries": industries_list(), "count": len(industries_list()),
                    "current": get_current_industry() or "(默认工厂)", "apply": apply_industry()})

    def _get_optmem_search(self, qs):
        # OptMem 全局记忆语义检索（optmem-search）
        from solo.memory import optmem_search
        q = qs().get("q", [""])[0]
        try:
            top_k = int(qs().get("top_k", ["5"])[0])
        except ValueError:
            top_k = 5
        self._json({"query": q, "hits": optmem_search(q, top_k=top_k)})


class _PostRoutesMixin:
    """POST 端点。body 参数为已解析的 JSON dict。"""

    def _post_config(self, body):
        # 仿工厂本体：前端提交 {models:[...], active, embedding} → 写回 config/model_config.json。
        # 兼容旧调用点：仍接受 {config: {provider: {...}}} 写 provider.yaml。
        if "models" in body or "active" in body:
            self._json(provider_mod.save_model_config(body))
        else:
            ok = api.write_config(body.get("config", {}))
            self._json({"saved": ok})

    def _post_monitor_ingest(self, body):
        # 设备监测：接入一条指标，走全链路 ingest→存储→告警→(auto)工单
        from solo.factory import monitor as mon
        device_id = body.get("device_id")
        metric = body.get("metric")
        value = body.get("value")
        if not device_id or not metric or value is None:
            self._json({"error": "需 device_id / metric / value"}, 400)
            return
        s = mon.Source(auto_ticket=bool(body.get("auto_ticket", True)))
        try:
            r = s.feed(device_id, metric, float(value))
        except (TypeError, ValueError):
            self._json({"error": "value 需为数字"}, 400)
            return
        self._json({"ingested": f"{device_id}.{metric}={value}",
                    "alerts": r["alerts"], "tickets": r["tickets"],
                    "latest": s.store.latest(device_id, metric)})

    def _post_monitor_protocol_http(self, body):
        # 协议直采（P0）：HTTP webhook 直采网关——真实设备/边缘网关 POST 指标，全链路落地
        # body: {device_id, metric, value} 或 {设备:{指标:值}}；自动_ticket 可选
        from solo.factory import protocols as proto
        g = proto.HttpIngestGateway(auto_ticket=bool(body.get("auto_ticket", True)))
        r = g.ingest(body)
        self._json(r)

    def _post_monitor_protocol_probe(self, body):
        # 协议直采（P0）：连接自检（TCP/HTTP/MQTT 等源连通状态）
        from solo.factory import protocols as proto
        try:
            src = proto.create_source(body.get("config") or {"protocol": "tcp"},
                                      auto_ticket=False)
            self._json(src.probe())
        except proto.ProtocolError as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _post_monitor_chain(self, body):
        # 规则链（P1）：新增/更新一条 JSON 告警规则链
        from solo.factory import monitor as mon
        action = body.get("action", "add")
        rc = mon.RuleChain()
        if action == "add":
            # 规则需包在 rule 字段内（避免规则的 action 与分发 action 冲突）
            rule = body.get("rule")
            if not isinstance(rule, dict):
                self._json({"error": "需 rule 字段（JSON 规则链对象）"}, 400)
                return
            try:
                saved = rc.add(rule)
            except ValueError as e:
                self._json({"error": str(e)}, 400)
                return
            self._json({"ok": True, "rule": saved, "count": len(rc.list())})
        elif action == "remove":
            self._json({"ok": rc.remove(body.get("id", "")), "count": len(rc.list())})
        elif action == "evaluate":
            # 手动评估一条指标：{device_id, metric, value}
            fired = rc.evaluate_point(body.get("device_id"), body.get("metric"),
                                      float(body.get("value", 0)))
            self._json({"ok": True, "fired": fired, "count": len(fired)})
        else:
            self._json({"error": f"unknown chain action: {action}"}, 400)

    def _post_monitor_ask(self, body):
        # 设备监测：AI 问数（自然语言查设备/告警/工单，先查库再回答）
        from solo.factory import monitor as mon
        q = (body.get("question") or "").strip()
        if not q:
            self._json({"error": "需 question"}, 400)
            return
        self._json(mon.MonitorAsk().ask(q))

    def _post_monitor_rule(self, body):
        # 设备监测：设置告警规则（阈值 + 可选突变检测）
        from solo.factory import monitor as mon
        device_id = body.get("device_id")
        metric = body.get("metric")
        if not device_id or not metric:
            self._json({"error": "需 device_id / metric"}, 400)
            return
        try:
            thr = float(body.get("threshold"))
        except (TypeError, ValueError):
            self._json({"error": "threshold 需为数字"}, 400)
            return
        store = mon.MetricStore()
        store.set_rule(device_id, metric, body.get("op", ">"), thr,
                       level=body.get("level", "medium"),
                       mutate_pct=body.get("mutate_pct"))
        rules = store.rules(device_id)
        self._json({"ok": True, "rule": rules[-1] if rules else None})

    def _post_monitor_ticket_state(self, body):
        # 设备监测：推进工单状态机 open → in_progress → done
        from solo.factory import monitor as mon
        r = mon.AlertEngine().ticket_state(
            body.get("ticket_id"), body.get("target"),
            body.get("note", ""))
        if "error" in r:
            self._json(r, 400)
            return
        self._json(r)

    def _post_monitor_demo(self, body):
        # 设备监测：一键端到端演示（模拟数据→告警→工单→AI问数）
        from solo.factory import monitor as mon
        try:
            rounds = int(body.get("rounds", 12))
        except (TypeError, ValueError):
            rounds = 12
        r = mon.run_demo(rounds=rounds)
        self._json({
            "metrics": r["metrics"], "firing_alerts": r["firing_alerts"],
            "total_alerts": r["total_alerts"], "tickets": r["tickets"],
            "q_high_temp": r["q_high_temp"]["answer"],
            "q_alerts": r["q_alerts"]["answer"],
            "q_max_temp": r["q_max_temp"]["answer"],
        })


    def _post_stats(self, body):
        # POST 数据分析（数据源对象：csv 或 db+table）
        rows = api.load_rows(body)
        self._reply_stats(rows, body.get("col"))

    def _post_remote(self, body):
        # 远程运维（FDE 现场 SSH 连接/执行/部署/日志）
        from solo.factory import ops as ops_mod
        act = body.get("action", "exec")
        host, user, port = body.get("host", ""), body.get("user"), body.get("port", 22)
        if not host:
            self._json({"error": "host 必填"}, 400)
            return
        try:
            if act == "test":
                self._json(ops_mod.test_connection(host, user, port))
            elif act == "deploy":
                # 默认 git pull + 容器重启（对齐 remote_deploy 语义）
                cmd = body.get("cmd") or "cd /app && git pull && docker compose up -d"
                self._json(ops_mod.run_command(host, cmd, user, port))
            elif act == "logs":
                self._json(ops_mod.remote_logs(host, user, port, body.get("cmd", "")))
            else:
                self._json(ops_mod.run_command(host, body.get("cmd", ""), user, port))
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _post_rdbms_connect(self, body):
        # 企业数据库接入（MySQL/Postgres）：测试连接 + 列出表
        from solo import data_connector as dc
        stype = body.get("type", "mysql")
        cfg = {"type": stype, "host": body.get("host", "127.0.0.1"),
               "port": int(body.get("port") or (3306 if stype == "mysql" else 5432)),
               "user": body.get("user", ""), "password": body.get("password", ""),
               "db": body.get("db", "")}
        try:
            dc.connect({**cfg, "table": "x"})  # 试连（无表也行，验证连接）
            # 列表：驱动可用时尝试
            import importlib
            mod = importlib.import_module("pymysql" if stype == "mysql" else "psycopg2")
            if stype == "mysql":
                conn = mod.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                                   password=cfg["password"], database=cfg["db"], connect_timeout=8)
                cur = conn.cursor()
                cur.execute("SHOW TABLES")
                tables = [r[0] for r in cur.fetchall()]
            else:
                conn = mod.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                                   password=cfg["password"], dbname=cfg["db"], connect_timeout=8)
                cur = conn.cursor()
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                tables = [r[0] for r in cur.fetchall()]
            cur.close(); conn.close()
            self._json({"ok": True, "type": stype, "host": cfg["host"], "tables": tables})
        except dc.DataSourceError as e:
            self._json({"ok": False, "error": str(e)}, 400)
        except ImportError:
            pkg = "pymysql" if stype == "mysql" else "psycopg2-binary"
            self._json({"ok": False, "error": f"驱动未装，请 pip install {pkg}"}, 400)
        except Exception as e:
            self._json({"ok": False, "error": str(e)}, 400)

    def _post_task(self, body):
        # 工单闭环（FDE 问题管理）+ 目标式任务控制面（task-new/gate/resolve/list_tasks）
        from solo.task import Task
        t = Task()
        cmd = body.get("cmd") or "new_issue"
        if cmd == "new_issue":
            self._json(t.new_issue(body.get("problem", ""), body.get("severity", "medium")))
        elif cmd == "diagnose":
            self._json(t.diagnose(body.get("id", ""), body.get("diagnosis", "")))
        elif cmd == "resolve":
            self._json(t.resolve_issue(body.get("id", ""), body.get("resolution", "")))
        elif cmd == "status":
            self._json(t.status(body.get("id", "")))
        elif cmd == "new":  # 目标式任务（task-new）
            task = t.new(body.get("goal", ""))
            self._json({"id": task["id"], "goal": task["goal"], "state": task["state"]})
        elif cmd == "gate":  # 决策门（task-gate）
            self._json(t.gate(body.get("id", ""), body.get("question", "")))
        elif cmd == "resolve_task":  # 解决所有待确认门（task-resolve）
            self._json(t.resolve(body.get("id", "")))
        elif cmd == "list_tasks":  # 目标式任务列表（task-status）
            self._json({"tasks": t.list(body.get("state"))})
        elif cmd == "transition":  # 工单状态机（P0）：确定性流转 + 操作审计
            self._json(t.transition(body.get("id", ""), body.get("target", ""),
                                    actor=body.get("actor", "user"),
                                    note=body.get("note", "")))
        elif cmd == "audit":  # 工单全生命周期审计（P0）
            self._json(t.issue_audit(body.get("id", "")))
        else:
            self._json({"issues": t.list_issues()})

    def _post_run(self, body):
        from solo import agent as agent_mod
        try:
            res = agent_mod.run(body.get("task", ""), tier=body.get("tier", "auto"))
            self._json(res)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _post_agent(self, body):
        from solo import agent as agent_mod
        try:
            res = agent_mod.run(body.get("task", ""), tier="auto",
                                csv_path=body.get("csv"), col=body.get("col"),
                                conversation_id=body.get("conversation_id"),
                                history=body.get("history"))
            self._json(res)
        except Exception as e:
            self._handle_error(e)

    def _post_toggle(self, body):
        suite, cap = body.get("suite"), body.get("capability")
        enabled = body.get("enabled")
        if suite in CAPABILITIES and cap in CAPABILITIES[suite]:
            CAPABILITIES[suite][cap]["enabled"] = enabled
            self._json({"ok": True, "capabilities": CAPABILITIES})
        else:
            self._json({"error": "invalid capability"}, 400)

    def _post_clean(self, body):
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
            return
        res = app_mod.data_clean(rows, method=body.get("method", "drop"),
                                 outlier=body.get("outlier", "iqr"))
        self._json({"input": res["input"], "output": res["output"],
                    "report": res["report"], "sample": res["sample"]})

    def _post_report(self, body):
        # P0-5: 生成数据概览 HTML 报告（对标 pandas-profiling）
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空"}, 400)
            return
        self._json(app_mod.data_report(rows))

    def _post_export(self, body):
        # P0-5: 导出 CSV（清洗后数据 / 原始数据）
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空"}, 400)
            return
        import csv as _csv
        import io
        buf = io.StringIO()
        writer = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        self._json({"csv": buf.getvalue()})

    def _post_datasource_columns(self, body):
        # 数据源列检测：读数据源返回列名+类型+预览（供清洗/分析选列）
        # 支持多文件 csvs（合并多表列）
        if body.get("csvs"):
            all_rows = []
            for cp in body["csvs"][:10]:
                p = api.data_path(cp) or api.safe_path(cp)
                if p:
                    from solo import data_connector as dc
                    try:
                        rows = dc.connect({"type": "csv", "path": p})
                        if rows:
                            all_rows.extend(rows)
                    except Exception:
                        pass
            rows = all_rows
        else:
            rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空"}, 400)
            return
        cols = list(rows[0].keys()) if rows else []
        types = {}
        for c in cols:
            vals = [r.get(c, "") for r in rows[:50] if r.get(c, "") != ""]
            types[c] = api.guess_col_type(vals)
        self._json({"columns": cols, "types": types, "total_rows": len(rows),
                    "preview": rows[:3]})

    def _post_ontology(self, body):
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
            return
        # 安全：relations 路径必须项目内（防任意文件读）
        relations = body.get("relations")
        if isinstance(relations, str):
            rel_path = api.safe_path(relations)
            if not rel_path:
                self._json({"error": "relations outside project"}, 400)
                return
            relations = rel_path
        res = app_mod.build_ontology(rows, entity=body.get("entity"),
                                     id_col=body.get("id"), relations=relations)
        if "error" in res:
            self._json({"error": res["error"]}, 400)
            return
        self._json(res)

    def _post_ontology_multi(self, body):
        # 企业级本体：多表 + 自动推断实体/外键
        from solo.factory import ontology as onto_mod
        data = self._load_multi_tables(body)
        if not data:
            self._json({"error": "无多表数据"}, 400)
            return
        # 自动 schema：每表一实体 + 外键推断（实体名美化：去前缀/下划线→驼峰）
        schema = self._multi_schema(data)
        o = onto_mod.Ontology()
        model = o.from_schema(schema, data)
        # 从图生成三元组（企业级关系）
        triples = len(model["graph"]["edges"])
        self._json({"entities": [ot["id"] for ot in model["object_types"]],
                    "triples": triples,
                    "nodes": len(model["graph"]["nodes"]),
                    "edges": len(model["graph"]["edges"]),
                    "link_types": [lt["id"] for lt in model["link_types"]],
                    "model": model})

    def _post_decisions(self, body):
        # 企业决策：多表数据源 → 声明式规则引擎 → 可解释行动清单
        from solo.factory import decisions as dec_mod
        data = body.get("data") or {}
        if not data:
            data = self._load_multi_tables(body)
        if not data:
            self._json({"error": "无数据源"}, 400)
            return
        res = dec_mod.run_decisions(data, model=body.get("model"),
                                    industry=body.get("industry"))
        res["tables"] = list(data.keys())
        # 行业联动：返回生效阈值覆盖（未显式传 industry 时跟随"当前行业"状态）
        from solo.factory.industry import apply_industry as _apply_ind
        res["industry"] = _apply_ind(body.get("industry"))
        self._json(res)

    def _post_memory_add(self, body):
        m = memory_mod.Memory()
        added = m.add_fact(body.get("text", ""), tags=["fact"])
        self._json({"added": added})

    def _post_memory_write(self, body):
        # 记忆写入决策层（P0）：对齐 Mem0 决策循环，写入前召回相似 → ADD/UPDATE/SKIP
        m = memory_mod.Memory()
        text = body.get("text", "")
        if not text:
            self._json({"error": "需 text"}, 400)
            return
        r = m.write(text, tags=body.get("tags"),
                    threshold=float(body.get("threshold", 0.6)))
        self._json(r)

    def _post_memory_update(self, body):
        # 记忆显式 UPDATE（P0）
        m = memory_mod.Memory()
        r = m.update_fact(body.get("target", ""), body.get("new_text", ""),
                          tags=body.get("tags"))
        self._json(r)

    def _post_memory_delete(self, body):
        # 记忆 DELETE（P0）
        m = memory_mod.Memory()
        r = m.delete_fact(text=body.get("text"), h=body.get("h"))
        self._json(r)

    def _post_survey(self, body):
        # 需求→验收生命周期（survey 打通入口，POST action 分发）
        act = body.get("action", "outline")
        try:
            if act == "outline":
                self._json(app_mod.survey_outline(body.get("industry")))
            elif act == "structure":
                self._json(app_mod.survey_structure(
                    body.get("name", ""), body.get("story", ""),
                    category=body.get("category", "生产"),
                    priority=body.get("priority", "P2"),
                    acceptance=body.get("acceptance"),
                    title=body.get("title")))
            elif act == "srs":
                self._json(app_mod.survey_srs(body.get("name", ""), title=body.get("title")))
            elif act == "acceptance":
                self._json(app_mod.survey_acceptance(body.get("name", "")))
            else:
                self._json({"error": f"unknown survey action: {act}"}, 400)
        except ValueError as e:
            self._json({"error": str(e)}, 400)

    def _post_skill_add(self, body):
        s = skill_mod.Skill()
        sk = s.add(body.get("name", ""), body.get("trigger", []), body.get("steps", []))
        self._json({"skill": sk})

    def _post_writing(self, body):
        from solo import writing as writing_mod
        if body.get("action") == "styles":
            self._json({"styles": writing_mod.list_styles()})
        elif body.get("action") == "rewrite":
            p = provider_mod.Provider.from_file()
            # 脱敏→改写→还原(防敏感信息泄露给LLM)
            custom = body.get("custom_words") or None
            self._json(provider_mod.mask_and_rewrite(
                body.get("text", ""), body.get("style", "tweet"),
                provider=p, custom_words=custom))
        elif body.get("action") == "ai-taste":
            # writing-ai-taste：AI 味自检（评分+建议+自洽结论）
            self._json(writing_mod.ai_taste(body.get("text", ""), style=body.get("style", "report")))
        elif body.get("action") == "write-natural":
            # writing-write-natural：风格改写 + AI味复检闭环
            p = provider_mod.Provider.from_file()
            self._json(writing_mod.write_natural(body.get("text", ""),
                                                 style=body.get("style", "tweet"), provider=p))
        elif body.get("action") == "evidence":
            # 写作证据账本 + 事实核查（P0）：防幻觉、可溯源
            from solo.factory import evidence as ev
            text = body.get("text", "")
            if not text:
                self._json({"error": "需 text（写作产出）"}, 400)
                return
            rows = api.load_rows(body)
            if not rows:
                # 无数据源：只出证据账本（全 unsupported），不造假
                result = ev.FactChecker([]).check(text)
            else:
                result = ev.fact_check(text, rows, col_map=body.get("col_map"))
            result["report"] = ev.render_report(result)
            self._json(result)
        else:
            self._json(writing_mod.scan(body.get("text", "")))

    def _post_code_review(self, body):
        # 代码审查（对标 CodeAgent）
        from solo import code as code_mod
        cg = code_mod.CodeGraph()
        cg.index(body.get("dir") or "solo")
        self._json(cg.review(body.get("file", "")))

    def _post_gen(self, body):
        try:
            if body.get("kind") == "code-agent":
                # CodeAgent 全链路: 生成+审查+测试
                from solo import code as code_mod
                ca = code_mod.CodeAgent()
                out = ca.implement(body.get("topic", ""), language=body.get("language", "python"))
                self._json({"output": out.get("files", {}).get("main.py", ""),
                            "score": out.get("score"),
                            "issues": [i["title"] for i in out.get("issues", [])][:10],
                            "summary": out.get("summary", "")})
                return
            if body.get("kind") in ("readme", "guide", "docstring"):
                from solo import writing as writing_mod
                out = writing_mod.generate_doc(body.get("topic", ""), kind=body.get("kind"))
            else:
                from solo import code as code_mod
                out = code_mod.generate_code(body.get("topic", ""))
            self._json({"output": out})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    # ---- CLI→web 回归：本体导出/聚合问答/检索（onto-to-nt/onto-answer/onto-search）----
    def _build_onto(self, rows, entity=None, id_col=None, industry=None):
        """从 rows 建本体，注入行业 col_cn（对齐 cli._onto_build，使行业化列名问答可答）。"""
        from solo.factory.ontology import Ontology
        col_cn = {}
        if industry:
            from solo.factory import industry as ind_mod
            cfg = ind_mod.load_industry(industry)
            col_cn = dict(cfg.get("col_cn") or {})
            if not entity and cfg.get("entity_cn"):
                entity = cfg["entity_cn"]
        o = Ontology(col_cn=col_cn)
        o.from_rows(rows, entity_name=entity, id_col=id_col)
        o.build()
        return o

    def _post_onto_nt(self, body):
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
            return
        o = self._build_onto(rows, body.get("entity"), body.get("id"), body.get("industry"))
        self._json({"nt": o.to_nt(), "entities": list(o.entities.keys()), "triples": len(o.triples)})

    def _post_onto_answer(self, body):
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
            return
        q = body.get("question", "")
        if not q:
            self._json({"error": "question 必填（如'有多少台设备'/'功率最大的设备'）"}, 400)
            return
        o = self._build_onto(rows, body.get("entity"), body.get("id"), body.get("industry"))
        self._json({"question": q, "answers": o.answer(q, entity=body.get("entity"))})

    def _post_onto_search(self, body):
        rows = api.load_rows(body)
        if not rows:
            self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
            return
        term = body.get("term", "")
        o = self._build_onto(rows, body.get("entity"), body.get("id"), body.get("industry"))
        self._json({"term": term, "hits": o.search(term, top_k=body.get("top_k", 5))})

    def _post_onto_semantic(self, body):
        # 本体语义贯通（P0）：多表关联 + 字段语义角色 + 语义一致性 + 统一实例图
        from solo.factory.ontology import semantic as sem
        if body.get("fields"):
            # 仅字段语义角色分类/一致性
            fields = body.get("fields")
            if isinstance(fields, str):
                fields = [f.strip() for f in fields.split(",") if f.strip()]
            self._json({"fields": sem.cross_field_semantics(fields),
                        "consistency": sem.semantic_consistency(fields)})
            return
        if body.get("blocks"):
            # 多板块语义贯通（monitor/task/memory 字段统一到本体语义层）
            self._json(sem.semantic_bridge(body.get("blocks")))
            return
        # 多表关联：data 或 csvs → 实体图 + 语义角色
        data = self._load_multi_tables(body)
        if not data:
            self._json({"error": "需 fields / blocks / 多表数据源(csvs 或 data)"}, 400)
            return
        self._json(sem.link_entities(data))

    # ---- CLI→web 回归：交付辅助 FDE D0/D1/D4（draft-questions/lexicon-draft/report-draft/to-factory-lexicon/to-review-items）----
    def _post_delivery(self, body):
        act = body.get("action", "draft-questions")
        ind = body.get("industry")
        try:
            from solo.factory.assist import (draft_questions, lexicon_draft,
                                             report_draft, report_draft_dict,
                                             to_factory_lexicon, to_review_items)
            rows = api.load_rows(body)
            if act in ("draft-questions", "lexicon-draft", "to-factory-lexicon", "to-review-items") and not rows:
                self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
                return
            if act == "draft-questions":
                qs = draft_questions(rows, body.get("entity"), limit=body.get("limit", 12), industry=ind)
                out = {"questions": qs, "count": len(qs)}
            elif act == "lexicon-draft":
                headers = list(rows[0].keys()) if rows else []
                lex = lexicon_draft(headers, rows[:30], industry=ind)
                out = {"columns": len(lex), "draft": lex}
            elif act == "report-draft":
                if body.get("json"):
                    out = report_draft_dict(kb=body.get("kb"), industry=ind, hit=body.get("hit", 0.0),
                                            questions_n=body.get("questions", 0), hits=body.get("hits", 0),
                                            asset_versions=body.get("asset_versions", 0))
                else:
                    md, ai = report_draft(kb=body.get("kb"), industry=ind, hit=body.get("hit", 0.0),
                                          questions_n=body.get("questions", 0), hits=body.get("hits", 0),
                                          asset_versions=body.get("asset_versions", 0), note=body.get("note", ""))
                    out = {"report": md}
                    if ai and ai.get("ok"):
                        out["ai_taste"] = {"score": ai["ai_score"], "note": ai["note"],
                                           "verdict": ai.get("verdict"),
                                           "suggestions": ai["suggestions"][:6],
                                           "hard_fails": ai["hard_fails"]}
            elif act == "to-factory-lexicon":
                headers = list(rows[0].keys()) if rows else []
                d = lexicon_draft(headers, rows[:30], industry=ind)
                out = to_factory_lexicon(d, table_name=body.get("table_name", "数据"),
                                         entity_cn=body.get("entity_cn"), industry=ind)
            elif act == "to-review-items":
                headers = list(rows[0].keys()) if rows else []
                d = lexicon_draft(headers, rows[:30], industry=ind)
                items = to_review_items(d)
                out = {"items": items, "count": len(items)}
            else:
                self._json({"error": f"unknown delivery action: {act}"}, 400)
                return
            if ind:
                from solo.factory.industry import apply_industry
                out["industry"] = apply_industry(ind)
            self._json(out)
        except ValueError as e:
            self._json({"error": str(e)}, 400)

    # ---- CLI→web 回归：行业联动（industry-list/industry-set/industry-current）----
    def _post_industry(self, body):
        from solo.factory.industry import rebuild_industry_artifacts, apply_industry, get_current_industry
        act = body.get("action", "set")
        if act == "set":
            rows = None
            if body.get("csv"):
                rows = api.load_rows(body)
            res = rebuild_industry_artifacts(industry=body.get("industry") or None, rows=rows,
                                             out_dir=body.get("out_dir") or None,
                                             questions_n=body.get("limit", 12))
            res["current"] = get_current_industry() or "(默认工厂)"
            if body.get("industry"):
                res["apply"] = apply_industry(body.get("industry"))
            self._json(res)
            return
        self._json({"current": get_current_industry() or "(默认工厂)", "apply": apply_industry()})

    # ---- CLI→web 回归：OptMem 全局记忆 note（optmem-note）----
    def _post_optmem_note(self, body):
        from solo.memory import optmem_note
        ok, msg = optmem_note(body.get("text", ""))
        self._json({"ok": ok, "message": msg})

    # ---- CLI→web 回归：代码审查（code-review，code_review.review_file 口径对齐）----
    def _post_code_review_file(self, body):
        from solo import code_review as cr
        path = api.safe_path(body.get("file", ""))
        if not path or not os.path.exists(path):
            self._json({"error": "文件不存在或不在项目内"}, 400)
            return
        res = cr.review_file(path, max_complexity=int(body.get("max_complexity", 10)),
                             strict_undefined=bool(body.get("strict_undefined", False)))
        self._json({"file": res["file"], "score": res["static_score"],
                    "issues": res["static_issues"]})

    # ---- 多表数据源加载 / schema 生成（多端点共用，降低 _post_ontology_multi 复杂度）----
    def _load_multi_tables(self, body):
        """从 body 读多表数据：优先 data dict，否则按 csvs 数组读文件。"""
        data = body.get("data") or {}
        if data:
            return data
        from solo import data_connector as dc
        for cp in (body.get("csvs") or [])[:10]:
            p = api.data_path(cp) or api.safe_path(cp)
            if p:
                try:
                    rows = dc.connect({"type": "csv", "path": p})
                    tbl = os.path.splitext(os.path.basename(p))[0]
                    data[tbl] = rows
                except Exception:
                    pass
        return data

    def _multi_schema(self, data):
        """每表一实体 + 外键推断（实体名美化：去前缀/下划线→驼峰）。"""
        schema = {"entities": [], "relations": []}
        for tbl, rows in data.items():
            if not rows:
                continue
            raw = tbl
            for pref in ("factory_", "Factory_", "tbl_", "T_"):
                if raw.lower().startswith(pref):
                    raw = raw[len(pref):]
                    break
            ent_name = "".join(w.capitalize() for w in raw.split("_") if w) or tbl
            ent = {"id": ent_name, "table": tbl, "key": "id",
                   "label": ent_name, "domain": "业务"}
            if "id" not in rows[0] and rows[0]:
                ent["key"] = list(rows[0].keys())[0]
            ent["attributes"] = [{"name": c, "type": "string"} for c in rows[0]] if rows else []
            schema["entities"].append(ent)
        return schema
