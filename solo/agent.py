# -*- coding: utf-8 -*-
"""agent.py — AI 原生对话路由（循环五态 + 工具路由）。

方法论（VISION §17 + AI原生）：
对话是主入口。用户自然语言 → agent 理解意图 → 路由到对应套件模块
（clean/stats/ontology/memory/skill/writing/gen/code）→ 执行 → 返回结果。

v1 路由：关键词启发式（零依赖，本地优先）。
v2 升级：LLM 意图识别（provider 远端）。
"""
from __future__ import annotations

import os

from solo import memory as memory_mod
from solo import provider as provider_mod
from solo import skill as skill_mod
from solo.factory import clean as clean_mod
from solo.factory import stats as stats_mod
from solo.factory import ontology as ontology_mod

# 意图 → 处理函数 路由表
INTENTS = {
    "task": ["新建任务", "记录任务", "task-new", "决策门", "任务状态", "跟进任务", "建一个任务"],
    "memory_search": ["查记忆", "回忆", "我记得", "记忆检索", "查一查记忆"],
    "clean": ["清洗", "clean", "去重", "缺失", "异常值", "数据清洗"],
    "stats": ["分析", "stats", "统计", "趋势", "spc", "控制图", "数据分析", "describe", "看 "],
    "ontology": ["本体", "建模", "ontology", "实体关系", "设备", "工单"],
    "skill": ["技能", "skill", "经验", "沉淀"],
    "writing": ["写作检查", "六维", "文风", "检查这段", "检查文本"],
    "gen": ["生成", "写一段", "generate", "写代码", "写文档", "写 readme", "写 readme", "写指南", "readme", "README"],
    "code_overview": ["代码库", "项目概览", "代码结构", "理解代码"],
    "setup": ["部署检查", "环境检查", "setup", "体检"],
    "config": ["查看配置", "看配置", "配置情况", "当前配置", "模型配置"],
    "capabilities": ["能力清单", "有哪些能力", "能力"],
}


def route(task: str) -> str:
    """判断任务意图（返回意图名）。关键词启发式。"""
    t = task.lower()
    for intent, keywords in INTENTS.items():
        if any(k in t for k in keywords):
            return intent
    return "chat"


def route_llm(task: str) -> str:
    """P1-6: LLM 意图识别。失败/不可用时回退关键词 route。"""
    try:
        p = provider_mod.Provider.from_file()
        if not p.local and not p.remote:
            return route(task)
        intent_list = ", ".join(INTENTS.keys())
        prompt = (f"判断以下用户请求属于哪个意图。可选意图: {intent_list}。"
                  f"只回答一个意图名，不要解释。\n请求: {task}\n意图:")
        text = p.complete(prompt, tier="local")
        intent = text.strip().lower().split()[0] if text else ""
        if intent in INTENTS:
            return intent
    except Exception:
        pass
    return route(task)


def run(task: str, mem_dir: str = None, skill_dir: str = None, tier: str = "auto",
        csv_path: str = None, col: str = None, conversation_id: str = None,
        history: list = None) -> dict:
    """AI 原生对话路由：理解意图 → 调用套件模块 → 返回结构化结果。

    csv_path/col 可由前端附带（工厂操作需要数据文件）。
    conversation_id/history 支持多轮对话（P0-6）：传入会话历史注入上下文。
    """
    m = memory_mod.Memory(mem_dir or memory_mod.DEFAULT_DIR)
    # P1-6: 关键词优先，无法判定时用 LLM 增强（仍回退关键词）
    intent = route(task)
    if intent == "chat" and not any(k in task for k in ("你好", "hi", "hello")):
        llm_intent = route_llm(task)
        if llm_intent != "chat":
            intent = llm_intent

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
        from solo import diagnostics as diag_mod
        res = diag_mod.check_environment()
        res["intent"] = "setup"
        return res
    if intent == "task":
        from solo.task import Task
        t = Task()
        task = t.new(task)
        # 自动 predict（决策可观察性最小种子）：记录预期，供后续验证
        t.predict(task["id"], f"任务「{task['goal']}」将被推进")
        return {"intent": "task", "id": task["id"], "goal": task["goal"],
                "state": task["state"], "prediction": task["id"]}
    if intent == "config":
        from solo import provider as p_mod
        cfg = p_mod.load_config()
        if not cfg:
            return {"intent": "config", "configured": False,
                    "hint": "未配置 provider.yaml。运行 `solo setup` 检查环境，复制 provider.yaml.example 为 provider.yaml 并填写。",
                    "memory_dir": m.dir}
        p = cfg.get("provider", {})
        out = {"intent": "config", "configured": True}
        for k in ("local", "remote", "embed"):
            item = p.get(k, {})
            clean = dict(item)
            if "api_key_env" in clean:
                clean["api_key_env"] = clean["api_key_env"] + " (从环境变量读, 不落盘)"
            out[k] = clean
        return out
    if intent == "skill":
        sk = skill_mod.Skill(skill_dir or skill_mod.DEFAULT_DIR)
        return {"intent": "skill", "skills": sk.list(), "memory_dir": m.dir}
    if intent == "capabilities":
        from solo import registry as registry_mod
        return {"intent": "capabilities", "capabilities": registry_mod.capabilities(), "memory_dir": m.dir}

    # ---- 兜底：对话（记忆装载 → 推理 → 记忆提交）----
    profile = m.profile_text()
    related = m.search(task, top_k=3)
    related_txt = "\n".join(f"- {f['text']}" for f in related)
    sk = skill_mod.Skill(skill_dir or skill_mod.DEFAULT_DIR)
    skill_hint = sk.build_prompt(task)
    # 身份 + 产品知识锚定：让模型知道自己是谁、能做什么、怎么用
    identity = """你是 SoloAgentKit —— 一个面向 FDE（工厂/前置部署工程师）的轻量化全栈 AI 助手，专为一人公司设计。
你的能力（全部真实可用）：
- 数据清洗 / 数据分析 / 本体建模（工厂套件，选数据源后执行）
- 写作（六维中文检查：错字/标点/语病/数字/去AI味/活人感）
- 代码（库理解/生成/审查）
- 技能库管理（沉淀可复用经验）
- 部署检查 / 配置查看
你的用法：
- 左侧导航进入各工作区（写作/代码/技能/配置/部署）
- 数据类能力需先选择数据文件或数据库
- 也可直接对话，用自然语言描述任务（如"清洗 xx.csv"）
版本 v0.5.6，零第三方依赖。"""
    context = f"{identity}\n\n用户画像:\n{profile}\n\n相关记忆:\n{related_txt}"
    # P0-6 多轮对话：注入会话历史（最近 6 轮）供延续性对话
    if history:
        hist_txt = "\n".join(f"{'用户' if h.get('role')=='user' else '助手'}: {h.get('content','')}"
                             for h in history[-6:])
        context += f"\n\n对话历史:\n{hist_txt}"
    context += f"\n\n用户问题: {task}"
    if skill_hint:
        context += f"\n\n适用经验:\n{skill_hint}"
    p = provider_mod.Provider.from_file()
    # agent 层模型分层（P1-9）：按任务复杂度选模型，而非 context 长度
    # 简单对话/短任务 → 本地(快/免费)；复杂任务(长文/报告/复杂分析) → 远端(强)
    complex_task = any(w in task for w in ("写一篇", "报告", "深度分析", "长文", "方案", "复盘", "论文"))
    remote_ready = bool(p.remote and p.remote.get("api_key_env")
                        and os.environ.get(p.remote.get("api_key_env")))
    tier = "remote" if (complex_task and remote_ready) else "local"
    # 配置健康检查：防止模型编造配置类信息（如 API key 名）
    cfg_ok = bool(provider_mod.load_config())
    if not cfg_ok:
        return {"intent": "chat", "tier": tier, "config_unready": True,
                "suggestion": "⚠️ 模型未配置。请运行 `solo setup` 检查环境，并按提示配置 provider.yaml（本地 ornith / 远端 DeepSeek，key 从环境变量读）。",
                "memory_dir": m.dir}
    # 明确引导：模型不得编造配置/环境信息，只答能力范围内
    guard = "\n\n重要约束：若用户询问配置、API key、环境变量、模型设置等，不要猜测或编造，统一指引运行 `solo setup` 和 `solo config` 查看。只回答你实际知道的、能力范围内的事。"
    text = p.complete(context + guard + "\n\n请给出简洁回复(中文):", tier=tier)
    m.add_fact(task, tags=["task"])
    return {"intent": "chat", "suggestion": text, "tier": tier, "memory_dir": m.dir}
