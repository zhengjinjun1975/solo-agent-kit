# -*- coding: utf-8 -*-
"""web_api.py — solo-agent-kit Web 后端业务逻辑（零依赖，可独立测试）。

从 web_server.py 拆出的纯业务层：
- 路径/数据解析辅助函数
- 每个 API 端点的处理函数（接收参数，返回 (dict, status_code)）
不依赖 HTTP handler 对象，可独立单测。

HTTP 路由/响应留在 web_server.py 的 SoloHandler。
"""
from __future__ import annotations

import os

from solo import provider as provider_mod
from solo import memory as memory_mod
from solo import skill as skill_mod
from solo.factory import stats as stats_mod
from solo.factory import clean as clean_mod
from solo.base import ApiError, get_logger

# ---- 路径/数据辅助（从 web_server 搬来，纯业务） ----

def safe_path(p: str) -> str:
    """路径参数白名单：只允许项目内路径（默认本地部署，防任意文件读）。

    项目根 = web_api.py 所在仓库根。绝对路径或超出项目根 → 返回 ""（调用方报错）。
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


def data_path(p: str) -> str:
    """数据文件路径白名单：放开到硬盘，但只允许数据文件扩展名。

    供硬盘级浏览后的数据读取（csv/db/sqlite/xlsx），拒绝任意文件读取。
    """
    if not p:
        return ""
    ALLOWED = (".csv", ".db", ".sqlite", ".xlsx")
    p = os.path.normpath(p.replace("\\", "/"))
    if os.path.isabs(p) and os.path.exists(p) and p.lower().endswith(ALLOWED):
        return p
    return ""


def load_rows(body: dict) -> list:
    """从请求体解析数据源并读取为行列表。"""
    from solo import data_connector as dc
    from solo.base import DataSourceError
    if "source" in body:
        src = dict(body["source"])
        if "path" in src:
            src["path"] = data_path(src["path"]) or safe_path(src["path"])
        return dc.connect(src)
    if body.get("csvs"):
        merged = []
        for cp in body["csvs"][:10]:
            p = data_path(cp) or safe_path(cp)
            if not p:
                continue
            stype = "xlsx" if p.lower().endswith(".xlsx") else "csv"
            try:
                merged.extend(dc.connect({"type": stype, "path": p}))
            except DataSourceError:
                continue
        return merged
    if body.get("csv"):
        p = data_path(body["csv"]) or safe_path(body["csv"])
        stype = "xlsx" if p.lower().endswith(".xlsx") else "csv"
        return dc.connect({"type": stype, "path": p}) if p else []
    if body.get("db"):
        p = data_path(body["db"]) or safe_path(body["db"])
        if body.get("table"):
            return dc.connect({"type": "sqlite", "path": p, "table": body["table"]}) if p else []
        if body.get("query"):
            return dc.connect({"type": "sql", "path": p, "query": body["query"]}) if p else []
    return []


def guess_col_type(vals: list) -> str:
    """推断列类型（复用 clean 的逻辑）。"""
    if not vals:
        return "empty"
    return clean_mod.guess_type(str(vals[0]))


def num(v):
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def build_report(rows: list, cols: list) -> dict:
    """构建数据概览报告（对标 pandas-profiling 的结构）。"""
    total = len(rows)
    missing = {}
    types = {}
    col_stats = {}
    for c in cols:
        vals = [r.get(c, "") for r in rows]
        non_empty = [v for v in vals if str(v).strip() != ""]
        missing[c] = total - len(non_empty)
        types[c] = guess_col_type(non_empty[:1])
        if types[c] in ("float", "integer"):
            nums = [float(v) for v in non_empty if num(v)]
            if nums:
                col_stats[c] = stats_mod.describe(nums)
    seen = set()
    dups = 0
    for r in rows:
        key = tuple(str(r.get(c, "")) for c in cols)
        if key in seen:
            dups += 1
        else:
            seen.add(key)
    return {
        "total_rows": total, "total_cols": len(cols), "columns": cols,
        "types": types, "missing": missing, "missing_total": sum(missing.values()),
        "duplicates": dups, "col_stats": col_stats, "preview": rows[:5],
    }


def write_config(config: dict) -> bool:
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


def setup_checks() -> dict:
    """部署检查：Python / Ollama / config / 记忆库。"""
    import sys
    import json
    import urllib.request
    checks = {}
    checks["python"] = {"ok": sys.version_info >= (3, 9),
                        "version": f"{sys.version_info.major}.{sys.version_info.minor}"}
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
        checks["ollama"] = {"ok": True, "models": models[:5]}
    except Exception:
        checks["ollama"] = {"ok": False, "error": "本地 Ollama 未运行"}
    cfg = provider_mod.load_config()
    checks["config"] = {"ok": bool(cfg), "has_provider_yaml": bool(cfg)}
    m = memory_mod.Memory()
    checks["memory"] = {"ok": True, "dir": m.dir, "facts": len(m._load(m._facts_path, []))}
    return {"checks": checks, "all_ok": all(c.get("ok", True) for c in checks.values())}


def deploy() -> dict:
    """真实部署：检查环境 → 启动 Ollama（若未运行）→ 验证模型可用。"""
    import sys
    import json
    import subprocess
    import time
    import urllib.request
    log = []
    result = {"ok": False, "steps": [], "logs": log}
    log.append(f"[1/4] Python {sys.version_info.major}.{sys.version_info.minor} {'✅' if sys.version_info >= (3, 9) else '❌'}")
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
        log.append(f"[2/4] Ollama 已在运行 ✅ 模型: {', '.join(models[:5]) or '无'}")
    except Exception:
        log.append("[2/4] Ollama 未运行，尝试启动…")
        ollama_path = None
        for cand in [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                     r"C:\Program Files\Ollama\ollama.exe"]:
            if os.path.exists(cand):
                ollama_path = cand
                break
        if ollama_path:
            try:
                subprocess.Popen([ollama_path, "serve"], creationflags=0x00000008)
                log.append("    → 已尝试启动 ollama.exe")
                time.sleep(3)
                try:
                    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
                        models = [m.get("name", "") for m in json.load(r).get("models", [])]
                    log.append(f"    ✅ Ollama 启动成功 模型: {', '.join(models[:5]) or '无'}")
                except Exception:
                    log.append("    ❌ Ollama 启动后仍未响应")
            except Exception as e:
                log.append(f"    ❌ 启动失败: {e}")
        else:
            log.append("    ❌ 未找到 ollama.exe，请手动安装/启动")
    cfg = provider_mod.load_config()
    log.append(f"[3/4] provider.yaml {'✅' if cfg else '❌ 未配置'}")
    m = memory_mod.Memory()
    facts = len(m._load(m._facts_path, []))
    log.append(f"[4/4] 记忆库 {facts} 条事实 ✅")
    result["ok"] = all("❌" not in l for l in log)
    result["steps"] = log
    return result


# ---- API 端点处理函数（返回 (dict, status)） ----

def handle_memory_search(q: str, top_k: int = 5) -> dict:
    m = memory_mod.Memory()
    return {"query": q, "results": [{"text": f["text"], "ts": f.get("ts", "")}
                                     for f in m.search(q, top_k=top_k)]}


def handle_stats(rows: list, col) -> tuple:
    """数据分析。rows 来自 load_rows；col 可自动探测。返回 (dict, status)。"""
    if not rows:
        return {"error": "数据源无效或为空"}, 400
    if not col:
        for r in rows:
            for k in r:
                if r.get(k, "").strip() and num(r.get(k)):
                    col = k
                    break
            if col:
                break
    if not col:
        return {"error": "未找到数值列，用 --col 指定"}, 400
    vals = [float(r[col]) for r in rows if col and r.get(col, "").strip() and num(r.get(col))]
    if not vals and col:
        for r in rows:
            for k in r:
                if k != col and r.get(k, "").strip() and num(r.get(k)):
                    col = k
                    break
            if col and any(num(r.get(col, "")) for r in rows[:5]):
                break
        vals = [float(r[col]) for r in rows if col and r.get(col, "").strip() and num(r.get(col))]
    if not vals:
        return {"error": "column not found or no numeric data"}, 400
    return {"column": col, "describe": stats_mod.describe(vals),
            "anomalies": stats_mod.detect_anomaly(vals, method="iqr"),
            "control_chart": stats_mod.control_chart(vals)}, 200


def handle_ontology(rows: list, body: dict) -> tuple:
    from solo.factory import ontology as onto_mod
    if not rows:
        return {"error": "数据源无效或为空（CSV路径或数据库表）"}, 400
    o = onto_mod.Ontology()
    relations = None
    if body.get("relations"):
        import json as _json
        rel_path = safe_path(body["relations"])
        if not rel_path:
            return {"error": "relations outside project"}, 400
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
    o.from_rows(rows, entity_name=body.get("entity"), id_col=body.get("id"), relations=relations)
    o.build()
    return {"entities": list(o.entities.keys()), "triples": len(o.triples),
            "summary": o.entity_summary()}, 200
