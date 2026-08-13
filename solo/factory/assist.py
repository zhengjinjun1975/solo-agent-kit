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
            # 措辞对齐引擎极值模板 "最X的Y"(如"功率最大的设备"), 保证规则引擎能答出
            questions.append(f"{col_cn}最大的{en}")
            if len(questions) >= limit:
                break
            questions.append(f"{col_cn}最小的{en}")
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


def to_factory_lexicon(draft, table_name="数据", entity_cn=None):
    """把 lexicon_draft 初稿转换为【工厂本体 lexicon 契约】格式。

    对齐 factory-ontology-kit 的 lexicon.json 结构，使 solo 起草的词典初稿
    能被工厂本体直接消费（attr_cn2en/type_cn2en/status_cn2en/entity_cn2en 等）。
    返回 {description, attr_cn2en, attr_en2cn, type_cn2en, status_cn2en,
          zone_cn2en, entity_cn2en, numeric_fields, field_aliases, value_fields}
    """
    attr_cn2en, attr_en2cn = {}, {}
    type_cn2en, status_cn2en, zone_cn2en = {}, {}, {}
    numeric_fields, value_fields, field_aliases = {}, {}, {}
    # 枚举列: 值→值(中文值直接映射自身), 按列名归类
    _TYPE_COLS = ("type", "类型", "category", "类别", "产品")
    _STATUS_COLS = ("status", "状态")
    _ZONE_COLS = ("workshop", "车间", "zone", "区域", "产线")
    for col, e in (draft or {}).items():
        cn = e.get("cn", "") or col
        typ = e.get("type", "string")
        enum = e.get("enum") or []
        ename = local_name(col)
        if enum:
            low = str(col).lower()
            # 跳过 id/编号/唯一标识 列(不是枚举类型)
            if any(k in low for k in ("id", "udi", "编号", "序号", "码", "_id")):
                continue
            target = type_cn2en
            if any(k in low for k in _STATUS_COLS):
                target = status_cn2en
            elif any(k in low for k in _ZONE_COLS):
                target = zone_cn2en
            elif any(k in low for k in _TYPE_COLS) or True:
                target = type_cn2en
            for v in enum:
                target.setdefault(v, v)
            value_fields[ename] = cn
            field_aliases.setdefault(ename, []).extend([cn, col])
        elif typ in ("integer", "decimal"):
            attr_cn2en[cn] = ename
            attr_en2cn[ename] = cn
            numeric_fields.setdefault(cn, ename)
        else:
            attr_cn2en[cn] = ename
            attr_en2cn[ename] = cn
    # 实体映射
    ent_cn = entity_cn or "设备"
    entity_cn2en = {ent_cn: table_name}
    return {
        "description": f"由 solo lexicon_draft 起草 ({table_name}, 对齐工厂本体契约)",
        "attr_cn2en": attr_cn2en,
        "attr_en2cn": attr_en2cn,
        "type_cn2en": type_cn2en,
        "status_cn2en": status_cn2en,
        "zone_cn2en": zone_cn2en,
        "entity_cn2en": entity_cn2en,
        "numeric_fields": numeric_fields,
        "field_aliases": field_aliases,
        "value_fields": value_fields,
    }


def to_review_items(draft):
    """把 lexicon_draft 词典初稿转成闭源 review.add 可消费的待确认项列表。

    对齐闭源 orchestrator 的 review.add 调用: (item_type, item_key, item_value)
      - attr_mapping: 数值/文本列 → (col_cn 中→英), value=引擎字段名建议
      - type_enum / status_enum: 有限枚举值 → 待人在环确认的枚举词
    返回 [(item_type, key, value), ...], 供闭源 ingest_lexicon 批量写入 review 队列。
    """
    items = []
    for col, e in (draft or {}).items():
        cn = e.get("cn", "") or col
        typ = e.get("type", "string")
        enum = e.get("enum") or []
        if enum:
            # 枚举列: 每条枚举值一条待确认(type_enum, 若含状态词则 status_enum)
            for v in enum:
                items.append(("type_enum", v, cn))
        elif typ in ("integer", "decimal"):
            items.append(("attr_mapping", cn, local_name(col)))
        else:
            items.append(("attr_mapping", cn, local_name(col)))
    return items


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


def report_draft_dict(*, kb: str, industry: str, hit: float, questions_n: int, hits: int,
                      asset_versions: int = 0, health: dict = None, baseline: float = None,
                      note: str = "") -> dict:
    """起草交付报告(结构化 dict, 对齐闭源 deliver.report 字段)。

    闭源 deliver.report() 返回 {kb, industry, 命中率:{baseline,current,提升},
    资产版本链, 资产版本数, 自进化健康度, 人在环审查, 遗留问题}。
    solo 草稿给出其中的 命中率/资产版本数/自进化健康度 初稿，FDE 补全后进闭源 deliver 渲染。
    """
    import datetime
    health = health or {}
    return {
        "kb": kb,
        "industry": industry,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "solo_draft": True,  # 标记 solo 草稿, 闭源 deliver 识别后可并入正式报告
        "命中率": {
            "baseline": baseline,
            "current": round(float(hit), 4),
            "提升": round(float(hit) - baseline, 4) if baseline is not None else None,
        },
        "资产版本数": asset_versions,
        "自进化健康度": {
            "hypotheses": health.get("hypotheses", 0),
            "accepted": health.get("accepted", 0),
            "rolled_back": health.get("rolled_back", 0),
        },
        "说明": note or "",
    }
