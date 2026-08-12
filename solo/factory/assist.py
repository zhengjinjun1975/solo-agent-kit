# -*- coding: utf-8 -*-
"""assist.py — FDE 交付辅助（solo 边界内：起草/建议，不碰核心算法）。

对齐 product-system-closed-loop 总纲：FDE(solo) 干"问题集起草/词典初稿/报告起草"辅助活。
零依赖，纯标准库。solo 只产出初稿/建议，最终确认在闭源人在环。

能力:
- draft_questions: 从数据生成 benchmark 候选问题集（D0）
- lexicon_draft:   从 CSV 列生成词典初稿（列→中文名/类型/枚举建议）（D1）
- report_draft:    起草交付报告（命中率/实体/资产）（D4）
"""
from __future__ import annotations

import json
import os
import re

from .ontology import guess_type, local_name

# 常见量词
_MEASURE = {"设备": "台", "机器": "台", "产品": "个", "项目": "个", "订单": "个",
            "船": "艘", "客户": "家", "书": "本", "图书": "本", "批次": "批", "测线": "条"}
_EXTREME_CN = {"最大": "最大", "最高": "最高", "最贵": "最贵", "最小": "最小", "最低": "最低"}
_STOP_CN = {"id", "编码", "编号", "序号", "UDI"}


def _col_cn(col: str) -> str:
    """列名 → 中文（剥 id/下划线/驼峰，简单启发式）。"""
    c = re.sub(r"[_\-]", " ", col).strip()
    c = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", c)
    parts = [p for p in c.split() if p]
    if not parts:
        return col
    # 英文单词不翻译, 保留原名作为展示; 已是中文(含中文)则直接返回
    if re.search(r"[\u4e00-\u9fff]", col):
        return col
    return col  # 英文列名保留英文, 由 FDE/词典补充中文


def _entity_name(entity_name: str) -> str:
    """实体名 → 中文量词匹配用的词。"""
    return entity_name or "记录"


def draft_questions(rows, entity_name: str = "设备", limit: int = 12):
    """从数据生成 benchmark 候选问题集（FDE 起草初稿，非最终）。

    策略:
      - 实体总数: 有多少[台/个]实体
      - 数值列极值: 最大/最小的[列名]
      - 枚举列: [列名]有哪些 / 列出所有[列名]
      - 文本列: 有哪些[name列]

    返回 [question, ...]。FDE 挑选/补全后进闭源 benchmark。
    """
    if not rows:
        return []
    questions = []
    en = _entity_name(entity_name)
    measure = _MEASURE.get(en, "个")
    questions.append(f"有多少{measure}{en}")

    if not isinstance(rows[0], dict):
        return questions
    headers = list(rows[0].keys())
    values = {h: [str(r.get(h, "")) for r in rows if r.get(h) is not None] for h in headers}
    for h in headers:
        if any(s in str(h).lower() for s in ("id", "udi", "编号", "序号")):
            continue
        vals = [v for v in values[h] if v.strip()]
        if not vals:
            continue
        t = guess_type(vals[0])
        col_cn = _col_cn(h)
        if t in ("integer", "decimal"):
            questions.append(f"{_EXTREME_CN.get('最大', '最大')}的{col_cn}")
            if len(questions) >= limit:
                break
            questions.append(f"{_EXTREME_CN.get('最小', '最小')}的{col_cn}")
        else:
            uniq = sorted(set(vals))
            if 1 < len(uniq) <= 8:
                questions.append(f"{col_cn}有哪些")
            elif h.lower() in ("name", "名称", "名字"):
                questions.append(f"有哪些{en}")
        if len(questions) >= limit:
            break
    return questions[:limit]


def lexicon_draft(headers, sample_rows=None):
    """从 CSV 列生成词典初稿（FDE 起草，供闭源 lexicon_agent 参考/人在环确认）。

    返回 { 列名: { "cn": 中文建议, "type": 类型, "enum": 枚举值(若有限), "suggest": 建议 } }
    """
    if sample_rows is None:
        sample_rows = []
    draft = {}
    for h in headers:
        vals = [str(r.get(h, "")) for r in sample_rows if r.get(h) is not None]
        vals = [v for v in vals if v.strip()]
        typ = guess_type(vals[0]) if vals else "string"
        uniq = sorted(set(vals)) if vals else []
        enum = uniq if (typ == "string" and 1 < len(uniq) <= 8) else None
        entry = {
            "cn": _col_cn(h),
            "type": typ,
            "enum": enum,
            "suggest": "",
        }
        if enum:
            entry["suggest"] = f"状态/类型枚举值: {'、'.join(enum[:6])} — 建议补 type_cn2en/status_cn2en"
        elif typ in ("integer", "decimal"):
            entry["suggest"] = f"数值列 — 建议补 attr_cn2en({_col_cn(h)}→{local_name(h)})"
        else:
            entry["suggest"] = f"文本列 — 建议确认是否需 field_alias 或 entity 映射"
        draft[h] = entry
    return draft


def report_draft(*, kb: str, industry: str, hit: float, questions_n: int, hits: int,
                 asset_versions: int = 0, health: dict = None, note: str = ""):
    """起草交付报告（markdown 初稿，FDE 补全后进闭源 deliver）。

    hit: 命中率 0.0-1.0; health: {hypotheses, accepted, rolled_back}
    """
    health = health or {}
    hyp = health.get("hypotheses", 0)
    acc = health.get("accepted", 0)
    rb = health.get("rolled_back", 0)
    lines = [
        "# 行业认知系统交付报告（初稿）",
        "",
        f"- **知识库**: `{kb}` ({industry})",
        f"- **问答命中率**: {hit:.0%}（{hits}/{questions_n} 题）",
        f"- **语义资产版本**: {asset_versions} 个",
        f"- **自进化健康度**: 假设 {hyp} 条, 合入 {acc}, 回滚 {rb}",
        "",
        "## 交付内容",
        "- 单机认知系统（开源引擎 + 闭源交付层）",
        "- 定制语义资产（本体/词典/知识库）",
        "- 自然语言问答能力",
        "",
        "## 说明",
        f"{note or '（由 FDE 补充：数据范围、行业场景、验收要点）'}",
        "",
        "> 本报告为 FDE 起草初稿，最终版由闭源交付流程生成并归档。",
    ]
    return "\n".join(lines)
