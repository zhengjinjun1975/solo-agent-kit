# -*- coding: utf-8 -*-
"""train.py — 培训材料能力面（操作手册 + FAQ）。

单一概念域：把系统能力清单（app.capabilities 单一事实来源）结构化地
展开成操作手册，把常见问题展开成 FAQ，一次性交付客户培训材料。

复用（极简，不重造）：
- app.capabilities()      能力清单（唯一来源，含功能描述）
- survey.Survey(...)      需求清单（生成使用场景章节，可选）
- writing.scan / ai_taste 生成后做中文质量自检

零额外依赖（纯标准库 + 已有 solo 模块）。
"""
from __future__ import annotations

import datetime

# 操作手册的通用操作步骤模板（能力 → 步骤化操作）
_STEP_TEMPLATE = [
    "打开「{name}」功能入口（{group} 套件）",
    "准备输入数据/参数：按界面提示填写或选择数据源",
    "配置关键参数：{name} 的必填项与默认值",
    "执行 {name} 操作，等待处理完成",
    "检查输出/结果：核对关键指标是否符合预期",
    "保存/导出：将结果存档或导出为报告文件",
]


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _flat_capabilities(capabilities: dict) -> list:
    """把 {组: {能力: {desc}}} 扁平化为 [{group, name, desc}]（确定性有序）。"""
    out = []
    for group, items in (capabilities or {}).items():
        for name, meta in items.items():
            out.append({"group": group, "name": name,
                        "desc": meta.get("desc", "") if isinstance(meta, dict) else str(meta)})
    return out


def manual(capabilities: dict = None, requirements: list = None,
           title: str = None) -> dict:
    """生成步骤化操作手册（markdown）。

    capabilities 缺省时取 app.capabilities() 唯一能力清单；
    requirements 可选（需求 → 使用场景章节，来自 survey）。
    返回 {title, markdown, sections, steps, scan, ai}。
    """
    if capabilities is None:
        from solo import app as app_mod  # noqa: PLC0415
        capabilities = app_mod.capabilities()
    caps = _flat_capabilities(capabilities)
    title = title or "系统操作手册"

    md = [f"# {title}", "", f"- 生成时间：{_now()}", f"- 功能模块：{len(caps)} 个",
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
    markdown = "\n".join(md).rstrip() + "\n"

    scan = ai = None
    try:
        from solo import writing as _w  # noqa: PLC0415
        scan = _w.scan(markdown)
        ai = _w.ai_taste(markdown, style="report")
    except Exception:  # noqa: BLE001
        scan = ai = {"ok": False, "note": "writing 未接入"}
    return {"title": title, "markdown": markdown, "sections": len(caps),
            "steps": step_count, "scan": scan, "ai": ai}


def faq(questions: list = None, title: str = None) -> dict:
    """生成 FAQ 问答清单（markdown）。

    questions: [{q, a}, ...]；缺省给一套通用占位问答。
    返回 {title, markdown, count}。
    """
    title = title or "常见问题 FAQ"
    items = list(questions) if questions else [
        {"q": "如何导入数据？", "a": "进入对应功能，选择数据源（CSV/Excel/数据库），确认列映射后导入。"},
        {"q": "分析结果如何导出？", "a": "在结果页点击导出，可生成 Excel 报告文件。"},
        {"q": "遇到报错怎么办？", "a": "记录错误信息与复现步骤，参照运维工单流程提交支持。"},
    ]
    md = [f"# {title}", "", f"- 生成时间：{_now()}", f"- 问答条目：{len(items)} 条", ""]
    for i, it in enumerate(items, 1):
        md += [f"### Q{i}. {it.get('q', '')}", "", it.get("a", ""), ""]
    return {"title": title, "markdown": "\n".join(md).rstrip() + "\n", "count": len(items)}
