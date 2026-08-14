# -*- coding: utf-8 -*-
"""app.py — 统一服务门面（Application 层）。

收敛 cli / web_server / web_api / agent 四处重复实现的同一业务到唯一入口：
- 数据清洗 / 数据分析（含唯一数值列探测）/ 数据概览报告
- 脱敏配置视图 / 环境检查 / 部署 / 能力清单 / 本体建模

三入口（cli / web / agent）只做「取参→分发→序列化」，业务逻辑单一事实来源在此。
纯收敛、不加新功能、不引入抽象层。
"""
from __future__ import annotations

import json
import os
import sys

from solo import provider as provider_mod
from solo import memory as memory_mod
from solo.factory import data as data_mod
from solo.factory import ontology as ontology_mod
from solo.base import is_num


# ---- 能力清单（唯一来源，取代 web_server 硬编码 dict + registry） ----
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


def capabilities() -> dict:
    """唯一能力清单（双套件）。"""
    return CAPABILITIES


# ---- 数据清洗 ----
def data_clean(rows: list, method: str = "drop", outlier: str = "iqr") -> dict:
    """工厂数据清洗。返回 {input, output, report, sample}。"""
    cl = data_mod.DataCleaner()
    out = cl.clean(rows, fill_missing=method, outlier_method=outlier)
    return {"input": len(rows), "output": len(out), "report": cl.report,
            "sample": out[:5]}


# ---- 数据分析（唯一数值列探测） ----
_ID_COL_HINTS = ("id", "编号", "序号", "主键", "udi", "_id")


def _is_id_like(col: str) -> bool:
    """判断列名是否为 id/编号/序号 主键类（统计时应跳过，避免把主键当数值列）。"""
    low = str(col).strip().lower()
    return any(k in low for k in _ID_COL_HINTS)


def _detect_numeric_col(rows: list) -> str:
    """唯一数值列探测：返回第一个含数值的列名；无则 None。

    跳过 id/编号/序号 主键类列（主键虽常为数字，但不是要分析的指标列），
    确保 factory-stats 默认分析到真实指标而非主键。

    原 cli._factory_stats / web_api.handle_stats / web_server 两处内联 / agent
    各自实现了一份数值列探测，行为还不一致。统一收敛于此。
    """
    for r in rows:
        for k in r:
            if _is_id_like(k):
                continue
            v = r.get(k, "")
            if str(v).strip() and is_num(v):
                return k
    # 全表无非 id 数值列 → 回退允许 id（避免无可分析列时反而空白）
    for r in rows:
        for k in r:
            v = r.get(k, "")
            if str(v).strip() and is_num(v):
                return k
    return None


def _col_values(rows: list, col: str) -> list:
    return [float(r[col]) for r in rows if col and r.get(col, "").strip() and is_num(r.get(col))]


def data_stats(rows: list, col: str = None) -> dict:
    """数据分析（描述/异常/SPC/趋势）。col 缺省时自动探测数值列。

    返回 dict；失败时含 "error" 键（web 据此判 400）。
    """
    if not rows:
        return {"error": "数据源无效或为空"}
    if not col:
        col = _detect_numeric_col(rows)
    vals = _col_values(rows, col)
    # 指定列无数值时，回退找第一个数值列（避免 400）
    if not vals and col:
        other = _detect_numeric_col(rows)
        if other and other != col:
            col = other
            vals = _col_values(rows, col)
    if not col:
        return {"error": "未找到数值列，用 --col 指定"}
    if not vals:
        return {"error": "column not found or no numeric data"}
    return {"column": col,
            "describe": data_mod.describe(vals),
            "anomalies": data_mod.detect_anomaly(vals, method="iqr"),
            "control_chart": data_mod.control_chart(vals),
            "trend": data_mod.trend(vals)}


# ---- 数据概览报告（对标 pandas-profiling） ----
def data_report(rows: list, cols: list = None) -> dict:
    """数据概览报告（盘点/类型/缺失/重复/统计/预览）。"""
    cols = cols or (list(rows[0].keys()) if rows else [])
    total = len(rows)
    missing = {}
    types = {}
    col_stats = {}
    for c in cols:
        vals = [r.get(c, "") for r in rows]
        non_empty = [v for v in vals if str(v).strip() != ""]
        missing[c] = total - len(non_empty)
        types[c] = data_mod.guess_type(str(non_empty[0])) if non_empty else "empty"
        if types[c] in ("float", "integer"):
            nums = [float(v) for v in non_empty if is_num(v)]
            if nums:
                col_stats[c] = data_mod.describe(nums)
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


# ---- 唯一脱敏配置视图 ----
def config_view() -> dict:
    """唯一脱敏配置视图（api_key 不泄露原文，用 has_key/api_key_status 占位）。

    返回仿工厂本体的扁平模型列表 + active + embedding + 旧 provider 形状兜底，
    对齐 web /api/config 与 cli config / agent config 三处输出。
    """
    payload = provider_mod.model_config_payload()
    if not payload.get("configured"):
        return {"configured": False, "config": {}, "hint": "未配置",
                "active": "", "models": [], "embedding": {}}
    payload["config"] = provider_mod.load_config()  # 旧 provider 形状兜底
    return payload


# ---- 环境检查（收敛 cli._setup / web_api.setup_checks / diagnostics） ----
def _ollama_models() -> list:
    import urllib.request
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
        return [m.get("name", "") for m in json.load(r).get("models", [])]


def check_environment() -> dict:
    """环境检查：Python / Ollama / config / 记忆库。返回 {checks, all_ok}。"""
    checks = {}
    checks["python"] = {"ok": sys.version_info >= (3, 9),
                        "version": f"{sys.version_info.major}.{sys.version_info.minor}"}
    try:
        checks["ollama"] = {"ok": True, "models": _ollama_models()[:5]}
    except Exception:
        checks["ollama"] = {"ok": False, "error": "本地 Ollama 未运行"}
    cfg = provider_mod.load_config()
    checks["config"] = {"ok": bool(cfg), "has_model_config": bool(cfg)}
    m = memory_mod.Memory()
    checks["memory"] = {"ok": True, "dir": m.dir,
                        "facts": len(m._load(m._facts_path, []))}
    return {"checks": checks,
            "all_ok": all(c.get("ok", True) for c in checks.values())}


def deploy() -> dict:
    """真实部署：检查环境 → 启动 Ollama（若未运行）→ 验证模型可用。"""
    import subprocess
    import time
    import urllib.request
    log = []
    result = {"ok": False, "steps": [], "logs": log}
    log.append(f"[1/4] Python {sys.version_info.major}.{sys.version_info.minor} {'✅' if sys.version_info >= (3, 9) else '❌'}")
    try:
        models = _ollama_models()
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
                    models = _ollama_models()
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


# ---- 本体建模 ----
def _resolve_relations(relations, entity=None):
    """解析 relations：文件路径 → dict；兼容多实体/object_properties 结构。"""
    if not relations:
        return None
    if isinstance(relations, str):  # 文件路径
        if not os.path.exists(relations):
            return None
        with open(relations, encoding="utf-8") as f:
            relations = json.load(f)
    if isinstance(relations, dict):
        if "object_properties" in relations:
            relations = relations["object_properties"]
        elif relations and all(isinstance(v, dict) and "object_properties" in v
                               for v in relations.values() if isinstance(v, dict)):
            ent = entity if (entity and entity in relations) else next(iter(relations))
            relations = relations[ent].get("object_properties", relations[ent])
    return relations


def build_ontology(rows: list, entity: str = None, id_col: str = None,
                   relations=None, industry: str = None) -> dict:
    """本体建模。relations 可为 dict 或 JSON 文件路径。

    industry: 行业名 → 注入行业 col_cn 列名中文映射，使聚合问答能答行业化列名
              （与 draft_questions 行业措辞一致，改行业即联动）。
    """
    if not rows:
        return {"error": "数据源无效或为空（CSV路径或数据库表）"}
    col_cn = {}
    if industry:
        from solo.factory import industry as ind_mod
        cfg = ind_mod.load_industry(industry)
        col_cn = dict(cfg.get("col_cn") or {})
    o = ontology_mod.Ontology(col_cn=col_cn)
    rel = _resolve_relations(relations, entity)
    o.from_rows(rows, entity_name=entity, id_col=id_col, relations=rel)
    o.build()
    return {"entities": list(o.entities.keys()), "triples": len(o.triples),
            "summary": o.entity_summary()}


# ---- 需求→验收生命周期（survey 打通入口）----
def survey_outline(industry: str = None) -> dict:
    """访谈提纲（行业数据驱动）。"""
    from solo.factory import survey as s
    return s.interview_outline(industry)


def survey_structure(name: str, story: str, category: str = "生产",
                     priority: str = "P2", acceptance: list = None,
                     title: str = None, dir: str = None) -> dict:
    """录入并结构化一条需求（Survey 生命周期，编号 R-xxx 单一事实来源）。"""
    from solo.factory import survey as s
    return s.Survey(name, dir=dir).collect(story, category=category, priority=priority,
                                           acceptance=acceptance, title=title)


def survey_srs(name: str, title: str = None, dir: str = None) -> dict:
    """生成 SRS 文档（含中文质量自检 scan + ai_taste）。"""
    from solo.factory import survey as s
    return s.Survey(name, dir=dir).to_srs(title=title)


def survey_acceptance(name: str, dir: str = None) -> dict:
    """生成验收清单（A-xxx）+ 勾稽防漏项检查。"""
    from solo.factory import survey as s
    sv = s.Survey(name, dir=dir)
    items = sv.prepare_acceptance()
    return {"acceptance": items, "count": len(items), "check": sv.check()}
