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
from .industry import load_industry, apply_industry

# 常见量词
_MEASURE = {"设备": "台", "机器": "台", "产品": "个", "项目": "个", "订单": "个",
            "船": "艘", "客户": "家", "书": "本", "图书": "本", "批次": "批", "测线": "条"}
_EXTREME_CN = {"最大": "最大", "最高": "最高", "最贵": "最贵", "最小": "最小", "最低": "最低"}
_STOP_CN = {"id", "编码", "编号", "序号", "UDI"}

# id/编号/序号 主键类列（不参与属性/枚举映射，避免污染词典/review/lexicon）
_ID_HINTS = ("id", "编号", "序号", "主键", "udi", "_id")
# 名称类列（名称/客户/产品名/name）——实体名而非"类型"，不污染 type_cn2en
_NAME_HINTS = ("名称", "客户", "产品名", "name")

# 常见中文枚举值 → 英文建议（词典/lexicon 非恒等映射：给中文值补英文键，供工厂本体消费）
_CN_EN = {
    "运行": "running", "待机": "standby", "停机": "stopped", "故障": "fault",
    "正常": "normal", "异常": "abnormal", "在用": "in_use", "备用": "standby",
    "车床": "lathe", "铣床": "milling", "球阀": "ball_valve", "闸阀": "gate_valve",
    "一车间": "workshop_1", "二车间": "workshop_2", "三车间": "workshop_3",
    "华东一厂": "plant_east_1", "华北一厂": "plant_north_1",
}


def _is_id_like(col: str) -> bool:
    """是否 id/编号/序号 主键类列。"""
    low = str(col).strip().lower()
    return any(k in low for k in _ID_HINTS)


def _is_name_like(col: str) -> bool:
    """是否名称类列（实体名/客户/产品名，非类型）。"""
    low = str(col).strip().lower()
    return any(k in low for k in _NAME_HINTS)


def _en_suggest(v: str) -> dict:
    """中文枚举值 → 英文建议（非恒等映射）。已知词查表；未知中文词标记需人工翻译。"""
    en = _CN_EN.get(str(v).strip())
    if en:
        return {"en": en, "needs_translation": False}
    if re.search(r"[\u4e00-\u9fff]", str(v)):
        return {"en": "", "needs_translation": True}  # 中文未知词 → 需人工确认英文
    return {"en": str(v), "needs_translation": False}  # 已是英文/数字 → 原样


# 常见工厂列名 → 中文（方法论统一: 对齐 factory 中文问答语义）
COL_CN_MAP = {
    "device_name": "设备名称", "deviceName": "设备名称", "name": "名称",
    "device_type": "设备类型", "deviceType": "设备类型", "type": "类型", "category": "分类", "类别": "类别",
    "status": "状态", "workshop": "车间", "zone": "区域", "region": "区域",
    "power_kw": "功率", "power": "功率", "capacity_mw": "容量", "capacity": "容量",
    "vibration_mm_s": "振动", "temp_c": "温度", "temperature": "温度", "current_a": "电流",
    "price": "价格", "成本": "成本", "stock": "库存", "quantity": "数量",
    "customer": "客户", "customer_name": "客户名称", "customer_type": "客户类型",
    "product": "产品", "product_type": "产品类型", "product_name": "产品名称",
    "unit": "机组", "unit_type": "机组类型", "fuel_type": "燃料类型", "fuel": "燃料",
    "quality": "质量", "grade": "等级", "batch": "批次", "lot": "批次",
    "date": "日期", "produce_date": "生产日期", "delivery_date": "交付日期",
    "load": "负荷", "output": "产量", "efficiency": "效率", "yield": "良率",
}


def _col_cn(col: str) -> str:
    """列名 → 中文（方法论统一: 常见工厂列名转中文, 对齐 factory 中文问答）。"""
    if col in COL_CN_MAP:
        return COL_CN_MAP[col]
    # 已是中文(含中文)则直接返回
    if re.search(r"[\u4e00-\u9fff]", col):
        return col
    # 剥 id/下划线/驼峰后的英文, 尝试精确匹配映射; 否则保留原名(FDE/词典补中文)
    c = re.sub(r"[_\-]", "", col).strip().lower()
    if c in COL_CN_MAP:
        return COL_CN_MAP[c]
    return col


def _entity_name(entity_name: str) -> str:
    """实体名 → 中文量词匹配用的词。"""
    return entity_name or "记录"


def _industry_ctx(industry: str = None) -> dict:
    """解析行业配置上下文（数据驱动联动入口）。

    返回 {kb, entity_cn, measure, col_cn}。行业未登记 → 默认值兜底（不报错）。
    供 draft_questions / lexicon_draft / to_factory_lexicon / report_draft 联动。
    """
    cfg = load_industry(industry)
    return {
        "kb": cfg.get("kb", "factory"),
        "entity_cn": cfg.get("entity_cn", "设备"),
        "measure": cfg.get("measure", "台"),
        "col_cn": dict(cfg.get("col_cn", {})),
    }


def _col_cn_for(col: str, col_cn: dict) -> str:
    """列名 → 中文：先查行业列名映射，再回退全局 COL_CN_MAP。"""
    if col in col_cn:
        return col_cn[col]
    c = re.sub(r"[_\-]", "", col).strip().lower()
    if c in col_cn:
        return col_cn[c]
    return _col_cn(col)


def draft_questions(rows, entity_name: str = None, limit: int = 12, industry: str = None):
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
    # 行业联动：未显式指定实体/量词时，从行业配置解析（改行业即联动问题集）
    ctx = _industry_ctx(industry)
    if not entity_name:
        entity_name = ctx["entity_cn"]
    en = _entity_name(entity_name)
    measure = _MEASURE.get(en, ctx["measure"])
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
        col_cn = _col_cn_for(h, ctx["col_cn"])
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


def lexicon_draft(headers, sample_rows=None, industry: str = None):
    """从 CSV 列生成词典初稿（FDE 起草，供闭源 lexicon_agent 参考/人在环确认）。

    返回 { 列名: { "cn": 中文建议, "type": 类型, "enum": 枚举值(若有限), "suggest": 建议 } }
    行业联动：列→中文 优先查行业列名映射（col_cn），再回退全局 COL_CN_MAP。
    """
    if sample_rows is None:
        sample_rows = []
    ctx = _industry_ctx(industry)
    draft = {}
    for h in headers:
        # id/编号/序号 主键类列：标记为 identifier，不进属性/枚举映射（不污染词典）
        if _is_id_like(h):
            draft[h] = {
                "cn": _col_cn_for(h, ctx["col_cn"]),
                "type": "identifier",
                "enum": None,
                "suggest": "主键/标识列，不参与属性或枚举映射",
            }
            continue
        vals = [str(r.get(h, "")) for r in sample_rows if r.get(h) is not None]
        vals = [v for v in vals if v.strip()]
        typ = guess_type(vals[0]) if vals else "string"
        uniq = sorted(set(vals)) if vals else []
        enum = uniq if (typ == "string" and 1 < len(uniq) <= 8) else None
        entry = {
            "cn": _col_cn_for(h, ctx["col_cn"]),
            "type": typ,
            "enum": enum,
            "suggest": "",
        }
        if enum:
            entry["suggest"] = f"状态/类型枚举值: {'、'.join(enum[:6])} — 建议补 type_cn2en/status_cn2en"
        elif typ in ("integer", "decimal"):
            entry["suggest"] = f"数值列 — 建议补 attr_cn2en({_col_cn_for(h, ctx['col_cn'])}→{local_name(h)})"
        else:
            entry["suggest"] = f"文本列 — 建议确认是否需 field_alias 或 entity 映射"
        draft[h] = entry
    return draft


def to_factory_lexicon(draft, table_name="数据", entity_cn=None, industry: str = None):
    """把 lexicon_draft 初稿转换为【工厂本体 lexicon 契约】格式。

    对齐 factory-ontology-kit 的 lexicon.json 结构，使 solo 起草的词典初稿
    能被工厂本体直接消费（attr_cn2en/type_cn2en/status_cn2en/entity_cn2en 等）。
    返回 {description, attr_cn2en, attr_en2cn, type_cn2en, status_cn2en,
          zone_cn2en, entity_cn2en, numeric_fields, field_aliases, value_fields}
    """
    attr_cn2en, attr_en2cn = {}, {}
    type_cn2en, status_cn2en, zone_cn2en = {}, {}, {}
    numeric_fields, value_fields, field_aliases = {}, {}, {}
    value_en_suggest = {}   # 中文枚举值 → 英文建议（非恒等映射）
    # 枚举列: 值→值(中文值直接映射自身), 按列名归类
    _TYPE_COLS = ("type", "类型", "category", "类别", "产品")
    _STATUS_COLS = ("status", "状态")
    _ZONE_COLS = ("workshop", "车间", "zone", "区域", "产线")
    for col, e in (draft or {}).items():
        low = str(col).lower()
        # 跳过 id/编号/唯一标识 列(不是枚举也不进属性映射, 不污染词典)
        if _is_id_like(col):
            continue
        cn = e.get("cn", "") or col
        typ = e.get("type", "string")
        enum = e.get("enum") or []
        ename = local_name(col)
        # 名称类列（名称/客户/产品名/name）是实体名而非"类型"，不进 type_cn2en
        is_name = _is_name_like(col)
        if enum and not is_name:
            target = status_cn2en
            if any(k in low for k in _STATUS_COLS):
                target = status_cn2en
            elif any(k in low for k in _ZONE_COLS):
                target = zone_cn2en
            else:
                target = type_cn2en
            for v in enum:
                target.setdefault(v, v)
                value_en_suggest.setdefault(str(v), _en_suggest(v))
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
    # 行业联动：未显式指定实体中文名时，从行业配置解析（如阀门制造→阀门）
    ctx = _industry_ctx(industry)
    ent_cn = entity_cn or ctx["entity_cn"]
    entity_cn2en = {ent_cn: table_name}
    # 公共工业词典协同合并：若兄弟仓库 factory-ontology-kit 可达（linkage 已加 sys.path），
    # 把公共词典(00基础/行业词典)合并进本初稿，让 solo 起草的词典自动带跨行业通用概念。
    # 合并失败/不可达时纯本地初稿（不破坏 solo 独立可用）。
    lexicon = {
        "description": f"由 solo lexicon_draft 起草 ({table_name}, 实体={ent_cn}, 对齐工厂本体契约, 行业kb={ctx['kb']})",
        "attr_cn2en": attr_cn2en,
        "attr_en2cn": attr_en2cn,
        "type_cn2en": type_cn2en,
        "status_cn2en": status_cn2en,
        "zone_cn2en": zone_cn2en,
        "entity_cn2en": entity_cn2en,
        "numeric_fields": numeric_fields,
        "field_aliases": field_aliases,
        "value_fields": value_fields,
        "value_en_suggest": value_en_suggest,
    }
    # 公共工业词典协同合并（尝试兄弟仓库 factory-ontology-kit 的 loader）
    # 行业 → 公共词典文件映射（与 factory-ontology industrial_dict 一致）
    _INDUSTRY_DICT_FILE = {
        "阀门": "01_valve_pump.json", "泵阀": "01_valve_pump.json",
        "化工": "02_fine_chem.json", "精细化工": "02_fine_chem.json",
        "地质": "03_geophysics.json", "地球物理": "03_geophysics.json",
    }
    try:
        import industrial_dict_loader as _idl
        _ind_dict = _INDUSTRY_DICT_FILE.get(industry, "00_basis.json")
        _files = ["00_basis.json"]
        if _ind_dict != "00_basis.json":
            _files.append(_ind_dict)
        lexicon = _idl.merge_industrial_dict(lexicon, _files)
        lexicon["_public_dict_merged"] = True
    except Exception:
        pass  # factory-ontology 不可达时纯本地初稿
    return lexicon


def to_review_items(draft):
    """把 lexicon_draft 词典初稿转成闭源 review.add 可消费的待确认项列表。

    对齐闭源 orchestrator 的 review.add 调用: (item_type, item_key, item_value)
      - attr_mapping: 数值/文本列 → (col_cn 中→英), value=引擎字段名建议
      - type_enum / status_enum: 有限枚举值 → 待人在环确认的枚举词
    返回 [(item_type, key, value), ...], 供闭源 ingest_lexicon 批量写入 review 队列。
    """
    items = []
    for col, e in (draft or {}).items():
        low = str(col).lower()
        # 过滤 id/编号/序号/唯一标识 列, 不污染 review 队列(与 to_factory_lexicon 一致)
        if _is_id_like(col):
            continue
        cn = e.get("cn", "") or col
        typ = e.get("type", "string")
        enum = e.get("enum") or []
        # 名称类列（名称/客户/产品名/name）是实体名, 不进枚举待确认, 仅作属性映射
        if enum and not _is_name_like(col):
            # 枚举列: 每条枚举值一条待确认(type_enum, 若含状态词则 status_enum)
            for v in enum:
                items.append(("type_enum", v, cn))
        elif typ in ("integer", "decimal"):
            items.append(("attr_mapping", cn, local_name(col)))
        else:
            items.append(("attr_mapping", cn, local_name(col)))
    return items


def report_draft(*, kb: str = None, industry: str = None, hit: float, questions_n: int, hits: int,
                 asset_versions: int = 0, health: dict = None, note: str = ""):
    """起草交付报告（markdown 初稿，FDE 补全后进闭源 deliver）。

    hit: 命中率 0.0-1.0; health: {hypotheses, accepted, rolled_back}
    行业联动：未显式指定 kb 时，从行业配置自动解析（industry→kb）。
    """
    ctx = _industry_ctx(industry)
    kb = kb or ctx["kb"]
    # 行业显示名：显式 industry 优先；否则用生效行业名（跟随"当前行业"状态）
    industry = industry or apply_industry()["industry"]
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
    md = "\n".join(lines)

    # AI味自检（生成→检测→提示）：接入 zh-writing-checker，给出评分与建议，不强制改写
    ai = None
    try:
        from solo import writing as _w  # noqa: PLC0415
        ai = _w.ai_taste(md, style="report")
    except Exception:  # noqa: BLE001
        ai = {"ok": False, "note": "zh-writing-checker 未接入"}
    return md, ai


def report_draft_dict(*, kb: str = None, industry: str = None, hit: float, questions_n: int, hits: int,
                      asset_versions: int = 0, health: dict = None, baseline: float = None,
                      note: str = "") -> dict:
    """起草交付报告(结构化 dict, 对齐闭源 deliver.report 字段)。

    闭源 deliver.report() 返回 {kb, industry, 命中率:{baseline,current,提升},
    资产版本链, 资产版本数, 自进化健康度, 人在环审查, 遗留问题}。
    solo 草稿给出其中的 命中率/资产版本数/自进化健康度 初稿，FDE 补全后进闭源 deliver 渲染。
    行业联动：未显式指定 kb 时从行业配置解析；industry 缺省时用行业默认实体名。
    """
    import datetime
    ctx = _industry_ctx(industry)
    kb = kb or ctx["kb"]
    # 行业显示名：显式 industry 优先；否则用生效行业名（跟随"当前行业"状态）
    industry = industry or apply_industry()["industry"]
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
