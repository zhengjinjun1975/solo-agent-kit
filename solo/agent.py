# -*- coding: utf-8 -*-
"""agent.py — AI 原生对话路由（循环五态 + 工具路由）。

方法论（VISION §17 + AI原生）：
对话是主入口。用户自然语言 → agent 理解意图 → 路由到对应套件模块
（clean/stats/ontology/memory/skill/writing/gen/code）→ 执行 → 返回结果。

v1 路由：关键词启发式（零依赖，本地优先）。
v2 升级：LLM 意图识别（provider 远端）。
"""
from __future__ import annotations

from solo import memory as memory_mod
from solo import provider as provider_mod
from solo import skill as skill_mod
from solo.factory import clean as clean_mod
from solo.factory import stats as stats_mod
from solo.factory import ontology as ontology_mod

# 意图 → 处理函数 路由表
INTENTS = {
    "memory_search": ["查记忆", "回忆", "我记得", "记忆检索", "查一查记忆"],
    "clean": ["清洗", "clean", "去重", "缺失", "异常值", "数据清洗"],
    "stats": ["分析", "stats", "统计", "趋势", "spc", "控制图", "数据分析", "describe", "看 "],
    "ontology": ["本体", "建模", "ontology", "实体关系", "设备", "工单"],
    "skill": ["技能", "skill", "经验", "沉淀"],
    "writing": ["写作检查", "六维", "文风", "检查这段", "检查文本"],
    "gen": ["生成", "写一段", "generate", "写代码", "写文档", "写 readme", "写 readme", "写指南", "readme", "README"],
    "code_overview": ["代码库", "项目概览", "代码结构", "理解代码"],
    "setup": ["部署检查", "环境检查", "setup", "体检"],
}


def route(task: str) -> str:
    """判断任务意图（返回意图名）。关键词启发式。"""
    t = task.lower()
    for intent, keywords in INTENTS.items():
        if any(k in t for k in keywords):
            return intent
    return "chat"


def run(task: str, mem_dir: str = None, skill_dir: str = None, tier: str = "auto",
        csv_path: str = None, col: str = None) -> dict:
    """AI 原生对话路由：理解意图 → 调用套件模块 → 返回结构化结果。

    csv_path/col 可由前端附带（工厂操作需要数据文件）。
    """
    m = memory_mod.Memory(mem_dir or memory_mod.DEFAULT_DIR)
    intent = route(task)

    # ---- 套件模块路由 ----
    if intent == "clean":
        path = csv_path or "examples/data/factory_sensor.csv"
        cl = clean_mod.DataCleaner()
        rows = cl.load_csv(path)
        out = cl.clean(rows, fill_missing="drop", outlier_method="iqr")
        return {"intent": "clean", "summary": f"清洗完成 {len(rows)}→{len(out)} 行",
                "report": cl.report, "memory_dir": m.dir}
    if intent == "stats":
        path = csv_path or "examples/data/factory_sensor.csv"
        cl = clean_mod.DataCleaner()
        rows = cl.load_csv(path)
        target = col
        if not target:
            for r in rows:
                for k in r:
                    if r.get(k, "").strip().replace(".", "").isdigit():
                        target = k
                        break
                if target:
                    break
        if not target:
            return {"intent": "stats", "error": "未找到数值列", "memory_dir": m.dir}
        vals = [float(r[target]) for r in rows if r.get(target, "").strip()]
        return {"intent": "stats", "column": target,
                "describe": stats_mod.describe(vals),
                "anomalies": stats_mod.detect_anomaly(vals, method="iqr"),
                "control_chart": stats_mod.control_chart(vals), "memory_dir": m.dir}
    if intent == "ontology":
        path = csv_path or "examples/data/factory_equipment.csv"
        o = ontology_mod.Ontology()
        o.from_csv(path, entity_name="equip", id_col="id")
        o.build()
        return {"intent": "ontology", "entities": list(o.entities.keys()),
                "triples": len(o.triples), "memory_dir": m.dir}
    if intent == "memory_search":
        results = [{"text": f["text"], "ts": f.get("ts", "")} for f in m.search(task, top_k=5)]
        return {"intent": "memory_search", "results": results, "memory_dir": m.dir}
    if intent == "writing":
        from solo import writing as writing_mod
        return {"intent": "writing", **writing_mod.scan(task), "memory_dir": m.dir}
    if intent == "code_overview":
        from solo import code as code_mod
        cg = code_mod.CodeGraph()
        n = cg.index("solo")
        return {"intent": "code_overview", "indexed": n, "symbols": len(cg.symbols),
                "overview": cg.overview(), "memory_dir": m.dir}
    if intent == "gen":
        from solo import gen as gen_mod
        kind = "readme" if any(k in task for k in ("readme", "README", "文档", "指南")) else "code"
        out = gen_mod.generate_doc(task, kind=kind) if kind != "code" else gen_mod.generate_code(task)
        return {"intent": "gen", "output": out, "memory_dir": m.dir}
    if intent == "setup":
        from solo.web_server import _setup_checks
        res = _setup_checks()
        res["intent"] = "setup"
        return res

    # ---- 兜底：对话（记忆装载 → 推理 → 记忆提交）----
    profile = m.profile_text()
    related = m.search(task, top_k=3)
    related_txt = "\n".join(f"- {f['text']}" for f in related)
    sk = skill_mod.Skill(skill_dir or skill_mod.DEFAULT_DIR)
    skill_hint = sk.build_prompt(task)
    context = f"任务: {task}\n\n用户画像:\n{profile}\n\n相关记忆:\n{related_txt}"
    if skill_hint:
        context += f"\n\n适用经验:\n{skill_hint}"
    p = provider_mod.Provider.from_file()
    # 兜底对话固定走本地（对话是高频轻量，不因 context 长误判复杂走远端）
    text = p.complete(context + "\n\n请给出简洁处理建议(中文):", tier="local")
    m.add_fact(task, tags=["task"])
    return {"intent": "chat", "suggestion": text, "memory_dir": m.dir}
