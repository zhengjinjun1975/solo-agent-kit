# -*- coding: utf-8 -*-
"""quote.py — 商务报价能力面（工时/成本估算 + 报价单生成）。

单一概念域：把一次 FDE 项目从「数据规模/质量/需求/复杂度」科学估出人天，
再到报价单（明细 + 汇总 + 条款），一步到位。

数据驱动（单一事实来源）：
- 数据规模     rows 数 → 数据工程人天（每千行定额）
- 数据质量     复用 data.audit.quality 的质量分(0~1) → 质量折损人天
- 需求数       复用 survey 结构化需求条数 → 每需求人天
- 建模复杂度   basic/medium/advanced → 复杂度系数
  各项相加 → 总人天；乘以单价 → 金额；加税费 → 报价总额。

复用（极简，不重造）：
- data.quality(rows)                    数据质量分
- survey.Survey(...).requirements       需求条数（可选）
- plugins.excel_report.quote_report     报价单出 xlsx

零额外依赖（xlsx 仅在导出时依赖 openpyxl）。
"""
from __future__ import annotations

import datetime

from .data import quality

# ═══ 估算参数（确定性常量：可调整，单一事实来源）═══
EFFORT = {
    "base_days": 2.0,            # 项目基础人天（沟通/环境/交付）
    "scale_per_k_rows": 0.5,     # 每 1000 行数据 → 人天
    "req_days": 0.8,             # 每条需求 → 人天
    "quality_penalty": 1.2,      # 质量每缺 0.1 → 基础人天加成倍数
    "complexity": {              # 建模复杂度系数
        "basic": 1.0,            #   简单报表/看板
        "medium": 1.6,           #   本体 + 规则决策
        "advanced": 2.4,         #   图谱 RAG + 多系统对接
    },
}
COMPLEXITY = tuple(EFFORT["complexity"])
DEFAULT_UNIT_PRICE = 3000.0      # 人天单价（元）
DEFAULT_TAX = 0.06               # 增值税率
DEFAULT_DEPOSIT = 0.3            # 首付款比例


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def quality_score(rows: list) -> float:
    """数据质量分(0~1)：由 quality 审计指标加权得到（数据驱动）。

    = 0.5×完整度(1-缺失率) + 0.3×去重度(1-重复率) + 0.2×干净度(1-异常率)。
    空数据返回 0（无数据可估，最差质量）。
    """
    if not rows:
        return 0.0
    q = quality(rows)
    m = q["metrics"]
    total = m["rows"]
    cells = max(total * q["total_cols"], 1)
    completeness = 1 - m["missing_total"] / cells
    dedup = 1 - m["duplicates"] / total
    clean = 1 - min(m["outliers"], total) / total
    score = 0.5 * completeness + 0.3 * dedup + 0.2 * clean
    return round(max(0.0, min(1.0, score)), 3)


def quality_level(score: float) -> str:
    """质量分 → 中文档位（报价话术）。"""
    if score >= 0.9:
        return "优"
    if score >= 0.75:
        return "良"
    if score >= 0.6:
        return "中"
    return "差"


def estimate_effort(rows: list = None, requirements: list = None,
                    complexity: str = "basic", quality: float = None) -> dict:
    """人天估算（数据驱动）。

    总人天 = (基础 + 规模 + 质量折损 + 需求数) × 复杂度系数。
    返回 {rows, requirements, complexity, quality, quality_level,
          breakdown{base,scale,quality,requirements}, total_days}。
    """
    if complexity not in COMPLEXITY:
        raise ValueError(f"复杂度需为 {COMPLEXITY} 之一，收到: {complexity!r}")
    rows = rows or []
    req_count = len(requirements or [])
    q = quality if quality is not None else quality_score(rows)

    base = EFFORT["base_days"]
    scale = (len(rows) / 1000.0) * EFFORT["scale_per_k_rows"]
    quality_extra = base * (1 - q) * EFFORT["quality_penalty"]
    req_extra = req_count * EFFORT["req_days"]
    ratio = EFFORT["complexity"][complexity]

    total = (base + scale + quality_extra + req_extra) * ratio
    return {
        "rows": len(rows),
        "requirements": req_count,
        "complexity": complexity,
        "quality": round(q, 3),
        "quality_level": quality_level(q),
        "breakdown": {
            "base": base,
            "scale": round(scale, 2),
            "quality": round(quality_extra, 2),
            "requirements": round(req_extra, 2),
        },
        "total_days": round(total, 1),
    }


# ═══════════════════════════ 报价单：明细 + 汇总 + 条款 ═══════════════════════════
def build_quote(project: str, scope: str, effort: dict = None,
                rows: list = None, requirements: list = None,
                complexity: str = "basic", unit_price: float = DEFAULT_UNIT_PRICE,
                tax: float = DEFAULT_TAX, deposit: float = DEFAULT_DEPOSIT,
                **terms) -> dict:
    """生成报价单结构（不出盘）。

    输入 effort（estimate_effort 输出）或原始参数（rows/requirements/complexity，
    内部调用 estimate_effort）。返回含 lines 明细 + totals 汇总 + terms 条款。
    """
    eff = effort or estimate_effort(rows, requirements, complexity)
    # 明细行：把 breakdown 各项拆成报价行（scale 为空则省略）
    lines = [
        {"item": "项目基础（沟通/环境/交付）", "days": eff["breakdown"]["base"],
         "unit_price": unit_price},
    ]
    if eff["breakdown"]["scale"] > 0:
        lines.append({"item": f"数据工程（{eff['rows']} 行）",
                      "days": eff["breakdown"]["scale"], "unit_price": unit_price})
    if eff["breakdown"]["quality"] > 0:
        lines.append({"item": f"数据质量治理（质量分 {eff['quality']}）",
                      "days": eff["breakdown"]["quality"], "unit_price": unit_price})
    if eff["breakdown"]["requirements"] > 0:
        lines.append({"item": f"需求实现（{eff['requirements']} 条）",
                      "days": eff["breakdown"]["requirements"], "unit_price": unit_price})
    for ln in lines:
        ln["amount"] = round(ln["days"] * ln["unit_price"], 2)

    subtotal = round(sum(ln["amount"] for ln in lines), 2)
    tax_amount = round(subtotal * tax, 2)
    total = round(subtotal + tax_amount, 2)
    default_terms = {
        "工期": f"{eff['total_days']} 人天（约 {max(1, round(eff['total_days'] / 3))} 周）",
        "付款": f"首付 {int(deposit * 100)}%，验收通过后结清尾款",
        "交付": "数据交付 + 方案文档 + 现场培训 + 运维知识库",
        "质保": "验收后免费质保 3 个月",
    }
    default_terms.update(terms)
    return {
        "project": project,
        "scope": scope,
        "effort": eff,
        "unit_price": unit_price,
        "tax_rate": tax,
        "lines": lines,
        "totals": {"subtotal": subtotal, "tax": tax_amount, "total": total,
                   "days": eff["total_days"]},
        "terms": default_terms,
        "quoted_at": _now(),
    }


def export_quote(quote: dict, path: str = None) -> dict:
    """报价单出 xlsx（复用 excel_report.quote_report）。不可用则降级返回结构。"""
    try:
        from solo.plugins import excel_report  # noqa: PLC0415
        return excel_report.quote_report(quote, path=path)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "quote": quote}
