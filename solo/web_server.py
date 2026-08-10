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
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import provider as provider_mod
from solo import memory as memory_mod
from solo import skill as skill_mod
from solo.factory import stats as stats_mod
from solo.factory import clean as clean_mod

PORT = 8743

# 能力清单（双套件）
CAPABILITIES = {
    "factory": {
        "clean": {"desc": "数据清洗（缺失/重复/异常值）", "enabled": True},
        "stats": {"desc": "数据分析（描述/趋势/SPC）", "enabled": True},
        "ontology": {"desc": "本体建模（设备/工单关系）", "enabled": True},
    },
    "personal": {
        "memory": {"desc": "三层两域记忆", "enabled": True},
        "skill": {"desc": "可复用经验提取", "enabled": True},
        "writing": {"desc": "六维写作检查", "enabled": True},
        "code": {"desc": "代码生成/审查/库理解", "enabled": True},
    },
}


class SoloHandler(BaseHTTPRequestHandler):
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
        if not full.startswith(os.path.normpath(web_dir)) or not os.path.exists(full):
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
                self._handle_api_get(path, urllib.parse.parse_qs(parsed.query))
            except Exception as e:
                self._json({"error": str(e), "code": 500}, 500)
        else:
            self._serve_static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            self._handle_api_post(path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._json({"error": str(e), "code": 500}, 500)

    def _handle_api_get(self, path, qs):
        if path == "/api/capabilities":
            self._json(CAPABILITIES)
        elif path == "/api/config":
            cfg = provider_mod.load_config()
            if not cfg:
                self._json({"configured": False, "config": {}, "hint": "未配置"})
            else:
                self._json({"configured": True, "config": cfg})
        elif path == "/api/memory":
            m = memory_mod.Memory()
            facts = m._load(m._facts_path, [])
            self._json({"facts": len(facts), "profile": m.profile_text()})
        elif path == "/api/skills":
            s = skill_mod.Skill()
            self._json({"skills": s.list()})
        elif path == "/api/memory-search":
            m = memory_mod.Memory()
            q = qs.get("q", [""])[0]
            results = [{"text": f["text"], "ts": f.get("ts", "")} for f in m.search(q, top_k=5)]
            self._json({"query": q, "results": results})
        elif path == "/api/code-overview":
            from solo import code as code_mod
            d = _safe_path(qs.get("dir", [""])[0])
            cg = code_mod.CodeGraph()
            n = cg.index(d or "solo")
            self._json({"indexed": n, "symbols": len(cg.symbols), "overview": cg.overview()})
        elif path == "/api/stats":
            # GET: csv+col 兼容；POST: 数据源对象
            if self.command == "POST":
                body = self._read_body()
                rows = _load_rows(body)
                col = body.get("col")
            else:
                csv_path = _safe_path(qs.get("csv", [""])[0])
                col = qs.get("col", [None])[0]
                if not csv_path or not os.path.exists(csv_path):
                    self._json({"error": "csv not found or outside project"}, 400)
                    return
                from solo import data_connector as dc
                rows = dc.connect({"type": "csv", "path": csv_path})
            if not rows:
                self._json({"error": "数据源无效或为空"}, 400)
                return
            if not col:
                for r in rows:
                    for k in r:
                        if r.get(k, "").strip() and _num(r.get(k)):
                            col = k
                            break
                    if col:
                        break
            if not col:
                self._json({"error": "未找到数值列，用 --col 指定"}, 400)
                return
            vals = [float(r[col]) for r in rows if col and r.get(col, "").strip() and _num(r.get(col))]
            if not vals:
                self._json({"error": "column not found or no numeric data"}, 400)
                return
            self._json({"column": col, "describe": stats_mod.describe(vals),
                        "anomalies": stats_mod.detect_anomaly(vals, method="iqr"),
                        "control_chart": stats_mod.control_chart(vals)})
        elif path == "/api/setup":
            self._json(_setup_checks())
        elif path == "/api/datasource":
            # 列出数据源信息：SQLite 表 / 检查 CSV
            from solo import data_connector as dc
            db_path = qs.get("db", [""])[0]
            csv_path = qs.get("csv", [""])[0]
            result = {"sources": []}
            if db_path:
                result["sources"].append({"type": "sqlite", "path": db_path,
                                          "tables": dc.list_tables(_safe_path(db_path))})
            if csv_path:
                sp = _safe_path(csv_path)
                import os as _os
                result["sources"].append({"type": "csv", "path": sp,
                                          "exists": bool(sp and _os.path.exists(sp))})
            self._json(result)
        elif path == "/api/browse":
            # 完整文件遍历：目录树导航（带 dir 参数，返回目录+文件，可上下级）
            import os as _os
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cur = _safe_path(qs.get("dir", [""])[0]) or root
            cur = cur if _os.path.isdir(cur) else root
            dirs, files = [], []
            try:
                for name in sorted(_os.listdir(cur)):
                    full = _os.path.join(cur, name)
                    rel = _os.path.relpath(full, root).replace("\\", "/")
                    if _os.path.isdir(full):
                        if name not in (".git", "__pycache__", "node_modules", ".venv", ".solo"):
                            dirs.append({"path": rel, "name": name, "dir": True})
                    else:
                        if name.endswith((".csv", ".db", ".sqlite", ".xlsx", ".json")):
                            files.append({"path": rel, "name": name, "dir": False})
            except Exception:
                pass
            parent = "" if cur == root else _os.path.relpath(_os.path.dirname(cur), root).replace("\\", "/")
            self._json({"dir": _os.path.relpath(cur, root).replace("\\", "/") or "/",
                        "parent": parent, "dirs": dirs, "files": files})
        elif path == "/api/db-connect":
            # 数据库对接：连接→测试→列出表
            from solo import data_connector as dc
            body = self._read_body()
            db = _safe_path(body.get("db", ""))
            if not db or not os.path.exists(db):
                self._json({"ok": False, "error": "数据库文件不存在"}, 400)
                return
            tables = dc.list_tables(db)
            if not tables:
                self._json({"ok": False, "error": "无法连接或库中无表"}, 400)
                return
            self._json({"ok": True, "db": db, "tables": tables})
        elif path == "/api/db-preview":
            # 数据库表预览（前几行）
            from solo import data_connector as dc
            body = self._read_body()
            db = _safe_path(body.get("db", ""))
            table = body.get("table", "")
            rows = dc.connect({"type": "sqlite", "path": db, "table": table})[:5]
            self._json({"rows": rows})
        else:
            self._json({"error": "unknown api"}, 404)

    def _handle_api_post(self, path):
        if path == "/api/config":
            body = self._read_body()
            ok = _write_config(body.get("config", {}))
            self._json({"saved": ok})
        elif path == "/api/stats":
            # POST 数据分析（数据源对象：csv 或 db+table）
            body = self._read_body()
            rows = _load_rows(body)
            col = body.get("col")
            if not rows:
                self._json({"error": "数据源无效或为空"}, 400)
                return
            if not col:
                for r in rows:
                    for k in r:
                        if r.get(k, "").strip() and _num(r.get(k)):
                            col = k
                            break
                    if col:
                        break
            if not col:
                self._json({"error": "未找到数值列"}, 400)
                return
            vals = [float(r[col]) for r in rows if col and r.get(col, "").strip() and _num(r.get(col))]
            if not vals:
                self._json({"error": "column not found or no numeric data"}, 400)
                return
            self._json({"column": col, "describe": stats_mod.describe(vals),
                        "anomalies": stats_mod.detect_anomaly(vals, method="iqr"),
                        "control_chart": stats_mod.control_chart(vals)})
        elif path == "/api/run":
            body = self._read_body()
            from solo import agent as agent_mod
            try:
                res = agent_mod.run(body.get("task", ""), tier=body.get("tier", "auto"))
                self._json(res)
            except Exception as e:
                self._json({"error": str(e)}, 500)
        elif path == "/api/agent":
            body = self._read_body()
            from solo import agent as agent_mod
            try:
                res = agent_mod.run(body.get("task", ""), tier="auto",
                                    csv_path=body.get("csv"), col=body.get("col"))
                self._json(res)
            except Exception as e:
                self._json({"error": str(e)}, 500)
        elif path == "/api/toggle":
            body = self._read_body()
            suite, cap = body.get("suite"), body.get("capability")
            enabled = body.get("enabled")
            if suite in CAPABILITIES and cap in CAPABILITIES[suite]:
                CAPABILITIES[suite][cap]["enabled"] = enabled
                self._json({"ok": True, "capabilities": CAPABILITIES})
            else:
                self._json({"error": "invalid capability"}, 400)
        elif path == "/api/clean":
            body = self._read_body()
            from solo import data_connector as dc
            rows = _load_rows(body)
            if not rows:
                self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
                return
            cl = clean_mod.DataCleaner()
            out = cl.clean(rows, fill_missing=body.get("method", "drop"),
                           outlier_method=body.get("outlier", "iqr"))
            self._json({"input": len(rows), "output": len(out), "report": cl.report,
                        "sample": out[:5]})
        elif path == "/api/datasource-columns":
            # 数据源列检测：读数据源返回列名+类型+预览（供清洗/分析选列）
            body = self._read_body()
            rows = _load_rows(body)
            if not rows:
                self._json({"error": "数据源无效或为空"}, 400)
                return
            cols = list(rows[0].keys()) if rows else []
            types = {}
            for c in cols:
                vals = [r.get(c, "") for r in rows[:50] if r.get(c, "") != ""]
                types[c] = _guess_col_type(vals)
            self._json({"columns": cols, "types": types, "total_rows": len(rows),
                        "preview": rows[:3]})
        elif path == "/api/ontology":
            from solo.factory import ontology as onto_mod
            body = self._read_body()
            o = onto_mod.Ontology()
            relations = None
            # 数据源：csv 或 db+table
            rows = _load_rows(body)
            if not rows:
                self._json({"error": "数据源无效或为空（CSV路径或数据库表）"}, 400)
                return
            if body.get("relations"):
                import json as _json
                rel_path = _safe_path(body["relations"])
                if not rel_path:
                    self._json({"error": "relations outside project"}, 400)
                    return
                with open(rel_path, encoding="utf-8") as f:
                    relations = _json.load(f)
                if isinstance(relations, dict) and "object_properties" in relations:
                    relations = relations["object_properties"]
                elif relations and all(isinstance(v, dict) and "object_properties" in v
                                       for v in relations.values() if isinstance(v, dict)):
                    ent = body.get("entity")
                    if ent not in relations:
                        ent = next(iter(relations))
                    relations = relations[ent].get("object_properties", relations[ent])
            o.from_rows(rows, entity_name=body.get("entity"),
                        id_col=body.get("id"), relations=relations)
            o.build()
            self._json({"entities": list(o.entities.keys()), "triples": len(o.triples),
                        "summary": o.entity_summary()})
        elif path == "/api/memory-add":
            body = self._read_body()
            m = memory_mod.Memory()
            added = m.add_fact(body.get("text", ""), tags=["fact"])
            self._json({"added": added})
        elif path == "/api/skill-add":
            body = self._read_body()
            s = skill_mod.Skill()
            sk = s.add(body.get("name", ""), body.get("trigger", []), body.get("steps", []))
            self._json({"skill": sk})
        elif path == "/api/writing":
            from solo import writing as writing_mod
            body = self._read_body()
            self._json(writing_mod.scan(body.get("text", "")))
        elif path == "/api/gen":
            from solo import gen as gen_mod
            body = self._read_body()
            try:
                if body.get("kind") in ("readme", "guide", "docstring"):
                    out = gen_mod.generate_doc(body.get("topic", ""), kind=body.get("kind"))
                else:
                    out = gen_mod.generate_code(body.get("topic", ""))
                self._json({"output": out})
            except Exception as e:
                self._json({"error": str(e)}, 500)
        else:
            self._json({"error": "unknown api"}, 404)

    def log_message(self, fmt, *args):
        pass  # 静默日志


def _setup_checks() -> dict:
    """部署检查：Python / Ollama / config / 记忆库。"""
    import sys
    checks = {}
    checks["python"] = {"ok": sys.version_info >= (3, 9),
                        "version": f"{sys.version_info.major}.{sys.version_info.minor}"}
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
        checks["ollama"] = {"ok": True, "models": models[:5]}
    except Exception:
        checks["ollama"] = {"ok": False, "error": "本地 Ollama 未运行"}
    cfg = provider_mod.load_config()
    checks["config"] = {"ok": bool(cfg), "has_provider_yaml": bool(cfg)}
    m = memory_mod.Memory()
    checks["memory"] = {"ok": True, "dir": m.dir,
                        "facts": len(m._load(m._facts_path, []))}
    return {"checks": checks,
            "all_ok": all(c.get("ok", True) for c in checks.values())}


def _safe_path(p: str) -> str:
    """路径参数白名单：只允许项目内路径（默认本地部署，防任意文件读）。

    项目根 = web_server.py 所在仓库根。绝对路径或超出项目根 → 返回 ""（调用方报错）。
    """
    if not p:
        return ""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
    p = p.replace("\\", "/")
    if os.path.isabs(p):
        full = p
    else:
        full = os.path.join(root, p)
    full = os.path.normpath(full)
    if full.startswith(os.path.normpath(root)):
        return full
    return ""


def _load_rows(body: dict) -> list:
    """从请求体解析数据源并读取为行列表。

    body 支持:
      {"csv": "路径"}                      CSV 文件
      {"db": "路径", "table": "表名"}       SQLite 表
      {"db": "路径", "query": "SQL"}        SQL 查询
      {"source": {...}}                     data_connector.connect 格式
    """
    from solo import data_connector as dc
    if "source" in body:
        src = dict(body["source"])
        if "path" in src:
            src["path"] = _safe_path(src["path"])
        return dc.connect(src)
    if body.get("csv"):
        p = _safe_path(body["csv"])
        return dc.connect({"type": "csv", "path": p}) if p else []
    if body.get("db"):
        p = _safe_path(body["db"])
        if body.get("table"):
            return dc.connect({"type": "sqlite", "path": p, "table": body["table"]}) if p else []
        if body.get("query"):
            return dc.connect({"type": "sql", "path": p, "query": body["query"]}) if p else []
    return []


def _guess_col_type(vals: list) -> str:
    """推断列类型（复用 clean 的逻辑）。"""
    from solo.factory.clean import guess_type
    if not vals:
        return "empty"
    return guess_type(str(vals[0]))


def _write_config(config: dict) -> bool:
    """写 provider.yaml（极简 YAML 序列化）。"""
    path = os.path.join(os.path.expanduser("~"), ".solo", "provider.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        lines = ["# solo-agent-kit 模型配置", "provider:"]
        for tier, meta in config.get("provider", {}).items():
            lines.append(f"  {tier}:")
            for k, v in meta.items():
                lines.append(f"    {k}: {v}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return True
    except Exception:
        return False


def _num(v):
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def main():
    ap = argparse.ArgumentParser(description="solo-agent-kit Web 后端")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = HTTPServer((args.host, args.port), SoloHandler)
    print(f"solo web 后端已启动: http://{args.host}:{args.port}  (Ctrl+C 停止)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.server_close()


if __name__ == "__main__":
    main()
