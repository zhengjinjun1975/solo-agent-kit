# -*- coding: utf-8 -*-
"""kernels/survey_core.py — 需求调研/交付验收 纯函数内核。

迁移自 factory/survey.py（interview_outline/structure_requirement/generate_srs/
build_acceptance/reconcile）与 train.py（manual/faq）。无状态、确定性。
消费原子：deliver-accept、deliver-train。
"""
from __future__ import annotations

import re
from datetime import datetime

CATEGORIES = ["生产", "质量", "设备", "数据", "集成", "运维", "其他"]
PRIORITIES = ["P0", "P1", "P2", "P3"]

_ACCEPT_RE = re.compile(
    r"([\u4e00-\u9fff]{2,8}(?:率|量|度|数|额))|"
    r"(提升|降低|减少|增加|支持|实现|提供)[\u4e00-\u9fff]{0,10}")


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def interview_outline(industry: str, entity_cn: str = "设备",
                      measure: str = "台", note: str = "") -> dict:
    """生成某行业的访谈提纲（行业语义数据驱动）。"""
    base = [
        "现状：目前业务怎么运转？最费人/最易错的一环在哪？",
        f"对象：请列举核心{entity_cn}（{measure}计）及其关键属性，哪些字段是关键？",
        "痛点：现阶段最头疼的问题是什么？多久发生一次、影响多大？",
        "期望：最想先解决的 1~3 件事是什么？做成什么样算'好'？",
        "约束：有无预算/工期/数据/合规限制？新方案要接什么系统？",
        "边界：哪些明确不做？责任界面如何划分？",
    ]
    questions = base[:]
    questions.append(
        f"行业(={industry})：围绕{entity_cn}（{measure}），针对{note or '行业要点'}"
        f"，现有管控/流程有哪些缺口？")
    return {"industry": industry, "entity_cn": entity_cn, "measure": measure,
            "note": note, "questions": questions}


def _auto_acceptance(story: str) -> list:
    m = _ACCEPT_RE.search(story or "")
    if m:
        return [f"验证{m.group(0)}可按预期观测"]
    return ["验证需求在主流程中可完整走通"]


def structure_requirement(story: str, category: str = "生产",
                          priority: str = "P2", acceptance: list = None,
                          title: str = None, req_id: str = "") -> dict:
    """用户故事 → 结构化需求条目。"""
    cat = (category or "").strip()
    if cat not in CATEGORIES:
        raise ValueError(f"分类需为 {CATEGORIES} 之一，收到: {cat!r}")
    pr = (priority or "").strip().upper()
    if pr not in PRIORITIES:
        raise ValueError(f"优先级需为 {PRIORITIES} 之一，收到: {pr!r}")
    story = (story or "").strip()
    if not story:
        raise ValueError("story（用户故事/痛点）不能为空")
    acc = list(acceptance) if acceptance else _auto_acceptance(story)
    return {"id": req_id, "title": (title or story[:24]).strip(), "story": story,
            "category": cat, "priority": pr, "acceptance": acc}


def build_acceptance(requirements: list) -> list:
    """结构化需求 → 验收清单（单一事实来源勾稽：R-xxx 每条可验收条款 → A-xxx）。"""
    out = []
    for r in requirements:
        rid = r.get("id", "")
        for i, clause in enumerate(r.get("acceptance", [])):
            out.append({"aid": f"A-{len(out) + 1:03d}", "rid": rid,
                        "title": r.get("title", ""), "clause": clause,
                        "result": "待验收", "evidence": ""})
    return out


def reconcile(requirements: list, acceptance: list) -> dict:
    """勾稽：需求↔验收条目双向对齐，防漏项。"""
    req_ids = {r.get("id") for r in requirements if r.get("id")}
    item_req = {a.get("rid") for a in acceptance}
    missing = sorted(req_ids - item_req)
    orphan = sorted(item_req - req_ids)
    results = {}
    for a in acceptance:
        results[a.get("result")] = results.get(a.get("result"), 0) + 1
    return {
        "ok": not missing and not orphan, "missing": missing, "orphan": orphan,
        "stats": {"requirements": len(req_ids), "items": len(acceptance),
                  "passed": results.get("通过", 0), "failed": results.get("未通过", 0),
                  "pending": results.get("待验收", 0)},
    }


def generate_srs(requirements: list, title: str = "需求规格说明书") -> dict:
    """结构化需求 → SRS markdown。返回 {"markdown", "req_n"}。"""
    reqs = [r for r in requirements if r.get("id")]
    md = [f"# {title}", "", f"- 生成时间：{now_ts()}",
          f"- 需求条目：{len(reqs)} 条（单一事实来源，编号唯一）", "", "## 需求清单", ""]
    for r in reqs:
        md += [f"### {r['id']} {r['title']}",
               f"- 分类：{r['category']}　优先级：{r['priority']}",
               f"- 用户故事/痛点：{r['story']}", "- 可验收条款："]
        for a in r.get("acceptance", []):
            md.append(f"  - {a}")
        md.append("")
    return {"markdown": "\n".join(md).rstrip() + "\n", "req_n": len(reqs)}


def reconcile_acceptance(acceptance: list) -> dict:
    """验收清单全过判定：所有条目 result==通过。"""
    passed = all(a.get("result") == "通过" for a in acceptance)
    return {"accept": passed and len(acceptance) > 0,
            "passed_n": sum(1 for a in acceptance if a.get("result") == "通过"),
            "total": len(acceptance)}


# ---- 培训/知识转移（迁移自 train.py）----
_STEP_TEMPLATE = [
    "进入{name}功能模块",
    "按页面提示选择{group}相关参数/数据源",
    "确认输入无误后执行，等待结果返回",
    "核对结果与预期，必要时导出留档",
]


def flat_capabilities(capabilities: dict) -> list:
    """{组: {能力: {desc}}} → [{group, name, desc}]（确定性有序）。"""
    out = []
    for group, items in (capabilities or {}).items():
        for name, meta in items.items():
            out.append({"group": group, "name": name,
                        "desc": meta.get("desc", "") if isinstance(meta, dict) else str(meta)})
    return out


def manual(capabilities: dict, requirements: list = None, title: str = None) -> dict:
    """生成步骤化操作手册（markdown）。"""
    caps = flat_capabilities(capabilities)
    title = title or "系统操作手册"
    md = [f"# {title}", "", f"- 生成时间：{now_ts()}", f"- 功能模块：{len(caps)} 个",
          "", "## 一、功能操作步骤", ""]
    step_count = 0
    for i, c in enumerate(caps, 1):
        md += [f"### {i}. {c['name']}——{c['desc'] or c['name']}"]
        steps = [t.format(name=c["name"], group=c["group"]) for t in _STEP_TEMPLATE]
        step_count += len(steps)
        md += [f"{j}. {s}" for j, s in enumerate(steps, 1)]
        md.append("")
    if requirements:
        reqs = [r for r in requirements if r.get("id")]
        md += ["## 二、典型使用场景", ""]
        for r in reqs:
            md += [f"- **{r['id']} {r['title']}**（{r.get('category', '')}）：{r.get('story', '')}"]
        md.append("")
    md += ["## 三、注意事项", "",
           "- 操作前请确认数据源已就绪、权限已开通",
           "- 涉及生产数据时先在测试环境验证",
           "- 异常处理详见《常见问题 FAQ》"]
    return {"title": title, "markdown": "\n".join(md).rstrip() + "\n",
            "sections": len(caps), "steps": step_count}


def faq(questions: list = None, title: str = None) -> dict:
    """生成 FAQ 问答清单（markdown）。"""
    title = title or "常见问题 FAQ"
    items = list(questions) if questions else [
        {"q": "如何导入数据？", "a": "进入对应功能，选择数据源（CSV/Excel/数据库），确认列映射后导入。"},
        {"q": "分析结果如何导出？", "a": "在结果页点击导出，可生成 Excel 报告文件。"},
        {"q": "遇到报错怎么办？", "a": "记录错误信息与复现步骤，参照运维工单流程提交支持。"},
    ]
    md = [f"# {title}", "", f"- 生成时间：{now_ts()}", f"- 问答条目：{len(items)} 条", ""]
    for i, it in enumerate(items, 1):
        md += [f"### Q{i}. {it.get('q', '')}", "", it.get("a", ""), ""]
    return {"title": title, "markdown": "\n".join(md).rstrip() + "\n",
            "count": len(items)}


def report_draft(kb: str = None, industry: str = None, hit: float = 0.0,
                 questions_n: int = 0, hits: int = 0, title: str = None) -> dict:
    """交付报告草稿（markdown）。"""
    title = title or "FDE 交付报告"
    rate = round(hits / questions_n * 100, 1) if questions_n else 0.0
    md = [f"# {title}", "",
          f"- 生成时间：{now_ts()}",
          f"- 知识库：{kb or '—'}　行业：{industry or '—'}",
          f"- 问答命中：{hits}/{questions_n}（{rate}%）　命中率阈值基线：{hit}",
          "", "## 交付结论", "",
          f"本交付覆盖 {questions_n} 个验收问题，命中 {hits} 个，命中率 {rate}%。"]
    return {"title": title, "markdown": "\n".join(md).rstrip() + "\n",
            "hit_rate": rate, "questions_n": questions_n, "hits": hits}


def transfer_checklist(requirements: list, title: str = "知识转移清单") -> list:
    """知识转移检查清单：需求 → 需转交的培训/文档条目。"""
    out = []
    for r in requirements or []:
        rid = r.get("id", "")
        out.append({"rid": rid, "title": r.get("title", ""),
                    "item": f"向甲方交接 {r.get('title', '')} 的操作方法与验收标准",
                    "owner": "乙方", "state": "待交接"})
    return out
