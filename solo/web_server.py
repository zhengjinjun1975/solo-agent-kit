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
        self.send_header("Access-Control-Allow-Origin", "*")
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
            d = qs.get("dir", [""])[0]
            cg = code_mod.CodeGraph()
            n = cg.index(d or ".")
            self._json({"indexed": n, "symbols": len(cg.symbols), "overview": cg.overview()})
        elif path == "/api/stats":
            csv_path = qs.get("csv", [""])[0]
            col = qs.get("col", [None])[0]
            if not csv_path or not os.path.exists(csv_path):
                self._json({"error": "csv not found"}, 400)
                return
            cl = clean_mod.DataCleaner()
            rows = cl.load_csv(csv_path)
            vals = [float(r[col]) for r in rows if col and r.get(col, "").strip() and _num(r.get(col))]
            if not vals:
                self._json({"error": "column not found or no numeric data"}, 400)
                return
            self._json({"column": col, "describe": stats_mod.describe(vals),
                        "anomalies": stats_mod.detect_anomaly(vals, method="iqr"),
                        "control_chart": stats_mod.control_chart(vals)})
        elif path == "/api/setup":
            self._json(_setup_checks())
        else:
            self._json({"error": "unknown api"}, 404)

    def _handle_api_post(self, path):
        if path == "/api/config":
            body = self._read_body()
            ok = _write_config(body.get("config", {}))
            self._json({"saved": ok})
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
            cl = clean_mod.DataCleaner()
            rows = cl.load_csv(body.get("csv", ""))
            out = cl.clean(rows, fill_missing=body.get("method", "drop"),
                           outlier_method=body.get("outlier", "iqr"))
            self._json({"input": len(rows), "output": len(out), "report": cl.report})
        elif path == "/api/ontology":
            from solo.factory import ontology as onto_mod
            body = self._read_body()
            o = onto_mod.Ontology()
            relations = None
            if body.get("relations"):
                import json as _json
                with open(body["relations"], encoding="utf-8") as f:
                    relations = _json.load(f)
                if isinstance(relations, dict) and "object_properties" in relations:
                    relations = relations["object_properties"]
                elif relations and all(isinstance(v, dict) and "object_properties" in v
                                       for v in relations.values() if isinstance(v, dict)):
                    ent = body.get("entity")
                    if ent not in relations:
                        ent = next(iter(relations))
                    relations = relations[ent].get("object_properties", relations[ent])
            o.from_csv(body.get("csv", ""), entity_name=body.get("entity"),
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
