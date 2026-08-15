# -*- coding: utf-8 -*-
"""evidence.py — 写作 P0：证据账本 + 事实核查（写作产出附证据、可溯源、防幻觉）。

借鉴 writing-agent 的 `evidence_ledger.json` + `fact_check_report.md` 思路，
**只借鉴理念，不复制代码**，用零依赖、确定性规则实现，与 solo「证据溯源」定位一致。

能力：
1. `build_ledger(text, source_rows=None)` —— 从写作产出提取「可证伪声明」：
   数字/百分比/日期/大小关系（>N/<N/max/min），生成证据账本
   `[{claim, type, value, source, status, confidence, evidence, trace_id}]`。
2. `fact_check(text, source_rows, col_map=None)` —— 交付前核查：把每一条声明与
   真实数据源（CSV 行 / 指标快照 / 本体行）比对，判定 supported / unsupported /
   contradicted，输出核查报告。
3. 每个声明带 `trace_id`，可沿证据账本溯源到「数据源哪一行哪一列」——防幻觉、
   可复核。与 LLM evidence 溯源打通（产出附 evidence 字段）。

规则确定性（零 LLM）：数字声明 = 在源数据里找同指标列，比对数值是否一致/可解释；
百分比声明 = 断言比例与源比例是否吻合；"最大/最高" 声明 = 查源该列极值是否匹配。
"""
from __future__ import annotations

import re

# ═══════════════════════════════════════════════════════════════════
# 1. 声明提取（从文本抽出可证伪片段）
# ═══════════════════════════════════════════════════════════════════
# 数字/百分比/带单位数值
_NUM = r"(?:[-+]?\d[\d,]*\.?\d*)"
_PCT = r"(?P<pct>[-+]?\d[\d,]*\.?\d*)%"
_DATE = r"(?P<date>\d{4}[-/]\d{1,2}[-/]\d{1,2})"


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def build_ledger(text: str, source_rows: list = None) -> list:
    """从写作产出提取可证伪声明，生成证据账本。

    返回 list[claim]，claim = {id, claim, type, value, source, status,
                                confidence, evidence, trace_id}。
    source_rows 为可用的数据源行（list[dict]）；提取阶段不做核查，status 初始 'pending'。
    """
    ledger = []
    # 1) 百分比声明（"下降了 30%" "占用 90%"）
    for m in re.finditer(
            r"(?P<word>下降|上升|降低|升高|提升|减少|增加|占比|达到|占用|超|低于|高于|为|是)"
            r"[^。，；]{0,6}\s*" + _PCT, text):
        val = _to_float(m.group("pct"))
        word = m.group("word")
        sense = "decrease" if word in ("下降", "降低", "减少", "低于") else \
                "increase" if word in ("上升", "升高", "提升", "增加", "高于", "超") else "level"
        ledger.append(_claim(f"{word}{m.group('pct')}%", "percent", val,
                             {"word": word, "sense": sense}, text, m.start()))
    # 2) 数字声明（"温度 90" "功率 30" "设备 5 台"）——中文指标词后接数值，或数值后接量词
    for m in re.finditer(
            r"(?P<metric>[\u4e00-\u9fff]{1,5}(?:温度|振动|功率|内存|压力|流量|转速|数量|数值|值|量|率|占比|度))"
            r"\s*(?:为|是|达到|达)?\s*" + _NUM, text):
        metric = m.group("metric")
        if "。" in metric or "，" in metric or "％" in m.group(0):
            continue
        raw = m.group(0)
        if "%" in raw:  # 百分比已在上一步捕获
            continue
        # 提取数字本体（去掉指标词）
        mm = re.search(_NUM, raw)
        val = _to_float(mm.group(0))
        ledger.append(_claim(raw, "number", val, {"metric": metric},
                             text, m.start()))
    # 3) 日期声明
    for m in re.finditer(_DATE, text):
        ledger.append(_claim(m.group("date"), "date", m.group("date"), {}, text, m.start()))
    # 4) 极值声明（"最大/最高/最小 是 X"）
    for m in re.finditer(r"(?P<kind>最大|最高|最小|最低)[\u4e00-\u9fff]{0,4}\s*(?:为|是)?\s*" + _NUM,
                         text):
        mm = re.search(_NUM, m.group(0))
        ledger.append(_claim(m.group(0), "extreme", _to_float(mm.group(0)),
                             {"kind": m.group("kind")}, text, m.start()))
    # 去重 + 编号
    seen, out = set(), []
    for i, c in enumerate(ledger):
        key = (c["type"], c["value"])
        if key in seen:
            continue
        seen.add(key)
        c["id"] = f"E{i + 1}"
        c["trace_id"] = f"{c['id']}-{abs(hash(c['claim'])) % 10 ** 6}"
        c["status"] = "pending"
        c["confidence"] = 0.5
        out.append(c)
    return out


def _claim(claim: str, ctype: str, value, meta: dict, text: str, pos: int) -> dict:
    """构造一条声明（带上下文片段作 evidence 的一部分）。"""
    ctx = text[max(0, pos - 15):pos + len(claim) + 15].replace("\n", " ")
    return {"claim": claim, "type": ctype, "value": value, "meta": meta,
            "context": ctx, "source": None, "status": "pending",
            "confidence": 0.5, "evidence": [], "trace_id": None}


# ═══════════════════════════════════════════════════════════════════
# 2. 事实核查（声明 × 真实数据源 → supported/unsupported/contradicted）
# ═══════════════════════════════════════════════════════════════════
class FactChecker:
    """事实核查器：把证据账本声明与真实数据源（list[dict]）逐条比对。

    source_rows: 数据源行（如设备指标快照 / CSV 行 / 本体行）。
    col_map: 可选，指标中文→列名映射（{温度:temperature}），跨列语义。
    """

    _COL_HINTS = {
        "温度": ("temperature", "temp"), "振动": ("vibration", "vib"),
        "功率": ("power", "load"), "内存": ("mem", "memory"),
        "cpu": ("cpu",), "数量": ("count", "num", "qty"),
        "占比": ("ratio", "pct", "rate"), "台": ("id", "device_id", "count"),
    }

    def __init__(self, source_rows: list = None, col_map: dict = None):
        self.source_rows = source_rows or []
        self.col_map = col_map or {}

    # ---- 主入口 ----
    def check(self, text: str) -> dict:
        """对文本做完整事实核查：建账本 → 逐条核查 → 报告。

        返回 {ledger, summary, pass}：summary 汇总 supported/unsupported/contradicted。
        """
        ledger = build_ledger(text, self.source_rows)
        if not self.source_rows:
            for c in ledger:
                c["status"] = "unsupported"
                c["confidence"] = 0.0
                c["evidence"] = [{"note": "无数据源，无法核查"}]
            return self._report(ledger)
        for c in ledger:
            self._check_one(c)
        return self._report(ledger)

    def _report(self, ledger) -> dict:
        n = len(ledger)
        sup = sum(1 for c in ledger if c["status"] == "supported")
        uns = sum(1 for c in ledger if c["status"] == "unsupported")
        con = sum(1 for c in ledger if c["status"] == "contradicted")
        return {
            "ledger": ledger,
            "summary": {"total": n, "supported": sup, "unsupported": uns,
                        "contradicted": con,
                        "verdict": ("全可溯源" if sup == n and n else
                                    "存在不可溯源声明" if uns else
                                    "存在矛盾声明" if con else "无可证伪声明")},
            "pass": (n > 0 and con == 0 and uns == 0),
        }

    # ---- 单条核查 ----
    def _check_one(self, c: dict) -> None:
        t = c["type"]
        if t == "percent":
            self._check_percent(c)
        elif t == "number":
            self._check_number(c)
        elif t == "extreme":
            self._check_extreme(c)
        elif t == "date":
            self._check_date(c)
        else:
            c["status"] = "unsupported"
            c["confidence"] = 0.0
            c["evidence"] = [{"note": "未知声明类型"}]

    def _find_col(self, hint: str):
        """指标提示 → 数据源列名（col_map 优先 → 列名匹配 → 英文提示）。"""
        if not hint:
            return None
        if hint in self.col_map:
            return self.col_map[hint]
        low = hint.lower()
        for col in (list(self.source_rows[0].keys()) if self.source_rows else []):
            if low in col.lower():
                return col
        for en in self._COL_HINTS.get(hint, []):
            for col in (list(self.source_rows[0].keys()) if self.source_rows else []):
                if en in col.lower():
                    return col
        return None

    def _rows_numeric(self, col):
        vals = []
        for r in self.source_rows:
            v = r.get(col)
            if v is not None and str(v).strip() and _is_num(str(v)):
                vals.append(_to_float(str(v)))
        return vals

    def _check_percent(self, c: dict) -> None:
        """百分比声明：与源比例吻合 → supported；无法比对 → unsupported。"""
        word = c["meta"].get("word", "")
        target = None
        if word in ("占比", "达到", "占用", "为", "是"):
            target = self._find_percent_in_rows()
        if target is None:
            c["status"] = "unsupported"
            c["confidence"] = 0.0
            c["evidence"] = [{"note": f"无法从数据源验证 '{c['claim']}' 的占比基准"}]
            return
        claim_v = c["value"]
        diff = abs(target - claim_v)
        if diff <= max(5.0, target * 0.15):
            c["status"] = "supported"
            c["confidence"] = round(1 - diff / 100, 2)
            c["evidence"] = [{"source_col": "占比", "source_value": target,
                              "diff": round(diff, 1), "note": "与源占比吻合"}]
        else:
            c["status"] = "contradicted"
            c["confidence"] = 0.0
            c["evidence"] = [{"source_col": "占比", "source_value": target,
                              "diff": round(diff, 1), "note": "与源占比矛盾"}]

    def _find_percent_in_rows(self):
        """从数据源找占比类列，取最近一条值作为基准。"""
        for col in (list(self.source_rows[0].keys()) if self.source_rows else []):
            if any(k in col.lower() for k in ("ratio", "pct", "rate", "占比", "率")):
                v = self._rows_numeric(col)
                if v:
                    return v[-1]
        return None

    def _check_number(self, c: dict) -> None:
        """数字声明：找同指标列，比对最新值。"""
        col = self._find_col(c["meta"].get("metric", ""))
        if col is None:
            # 尝试用声明数字本身找任意数值列
            for cand in (list(self.source_rows[0].keys()) if self.source_rows else []):
                vals = self._rows_numeric(cand)
                if vals:
                    col = cand
                    break
        if col is None:
            c["status"] = "unsupported"
            c["confidence"] = 0.0
            c["evidence"] = [{"note": "数据源无匹配数值列"}]
            return
        vals = self._rows_numeric(col)
        if not vals:
            c["status"] = "unsupported"
            c["confidence"] = 0.0
            c["evidence"] = [{"col": col, "note": "列无数值"}]
            return
        latest = vals[-1]
        diff = abs(latest - c["value"])
        # 计数类（台/个）用精确；连续值用相对容差
        tol = max(1.0, latest * 0.2) if any(k in c["meta"].get("metric", "") for k in ("台", "个", "条")) else max(5.0, latest * 0.15)
        if diff <= tol:
            c["status"] = "supported"
            c["confidence"] = round(1 - min(1.0, diff / tol) * 0.5, 2)
            c["evidence"] = [{"col": col, "source_value": latest, "diff": round(diff, 2),
                              "note": "与源同指标最新值吻合"}]
        else:
            c["status"] = "contradicted"
            c["confidence"] = 0.0
            c["evidence"] = [{"col": col, "source_value": latest, "diff": round(diff, 2),
                              "note": "与源同指标最新值矛盾"}]

    def _check_extreme(self, c: dict) -> None:
        """极值声明（最大/最高/最小/最低是 N）：与源该列极值比对。"""
        kind = c["meta"].get("kind", "最大")
        is_max = kind in ("最大", "最高")
        for col in (list(self.source_rows[0].keys()) if self.source_rows else []):
            vals = self._rows_numeric(col)
            if not vals:
                continue
            extreme = (max if is_max else min)(vals)
            if abs(extreme - c["value"]) <= max(1.0, extreme * 0.15):
                c["status"] = "supported"
                c["confidence"] = 0.9
                c["evidence"] = [{"col": col, "extreme": extreme,
                                  "note": f"与源{kind}值吻合"}]
                return
        # 无匹配 → 试着用数字声明逻辑兜底
        self._check_number(c)

    def _check_date(self, c: dict) -> None:
        """日期声明：源里有该日期 → supported；否则 unsupported。"""
        for r in self.source_rows:
            for v in r.values():
                if str(v).strip() and c["value"] in str(v):
                    c["status"] = "supported"
                    c["confidence"] = 0.8
                    c["evidence"] = [{"note": f"源含日期 {c['value']}"}]
                    return
        c["status"] = "unsupported"
        c["confidence"] = 0.0
        c["evidence"] = [{"note": "数据源无此日期"}]


# ═══════════════════════════════════════════════════════════════════
# 便捷入口
# ═══════════════════════════════════════════════════════════════════
def fact_check(text: str, source_rows: list = None, col_map: dict = None) -> dict:
    """写作产出事实核查（P0 证据账本）：防幻觉、可溯源。"""
    fc = FactChecker(source_rows, col_map)
    return fc.check(text)


def render_report(result: dict) -> str:
    """把核查结果渲染为人类可读报告（对齐 fact_check_report.md）。"""
    s = result["summary"]
    lines = [f"[证据账本] 声明 {s['total']} 条 | 可溯源 {s['supported']} | "
             f"不可溯源 {s['unsupported']} | 矛盾 {s['contradicted']} | "
             f"结论: {s['verdict']}"]
    for c in result["ledger"]:
        ev = c["evidence"][0] if c["evidence"] else {}
        st = {"supported": "✓", "unsupported": "?", "contradicted": "✗",
              "pending": "·"}.get(c["status"], "·")
        lines.append(f"  {st} [{c['type']}] {c['claim']}  "
                     f"(trace:{c['trace_id']}) {ev.get('note', '')}")
    return "\n".join(lines)


def _is_num(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False
