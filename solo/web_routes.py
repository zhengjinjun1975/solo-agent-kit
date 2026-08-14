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
        # 工单闭环（FDE 问题管理）
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
