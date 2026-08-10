# -*- coding: utf-8 -*-
"""desensitize.py — 写作脱敏（零依赖）。

FDE 现场写作可能含敏感信息：客户名/厂区名/IP/手机号/邮箱/金额/序列号。
写作文本先脱敏(掩码)再交给 LLM 改写, 改写完成后按映射还原, 防泄露。

设计：
  mask(text)   → (masked_text, mapping)   敏感信息→占位符 {{TYPE_N}}
  restore(text, mapping) → 原文本           占位符→原始敏感信息
  mask_and_rewrite(text, style, provider) → 脱敏→改写→还原 一站式
"""
from __future__ import annotations

import re

# 敏感信息识别规则：类型 -> 正则
# 数字类用 (?<!\d)(?!\d) 而非 \b——中文与数字间无 \b 边界, 会漏匹配
RULES = [
    # IP 地址
    ("IP", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")),
    # 手机号(中国大陆 1[3-9]\d{9})
    ("PHONE", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    # 座机(区号-号码)
    ("TEL", re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")),
    # 邮箱
    ("EMAIL", re.compile(r"(?<!\w)[\w.+-]+@[\w-]+\.[\w.]+(?!\w)")),
    # 金额(¥/￥ + 数字 + 元/万/亿)
    ("AMOUNT", re.compile(r"[¥￥]\s*\d[\d,]*\.?\d*\s*(?:万|亿|元|万元|亿元)?" )),
    # 身份证号(18位)
    ("ID", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    # 域名
    ("DOMAIN", re.compile(r"(?<!\w)(?:[a-z0-9-]+\.)+[a-z]{2,}(?!\w)")),
    # 长数字串(设备序列号等, >=10位)
    ("SERIAL", re.compile(r"(?<!\d)\d{10,}(?!\d)")),
]

# 掩码展示: 保留首尾字符, 中间用 * 遮挡(客户名/厂区名等自定义词用)
def _mask_token(token: str, keep: int = 2) -> str:
    if len(token) <= keep * 2:
        return token[0] + "*" * (len(token) - 1)
    return token[:keep] + "*" * (len(token) - keep * 2) + token[-keep:]


def mask(text: str, custom_words: list = None) -> tuple:
    """脱敏文本, 返回 (masked_text, mapping)。

    custom_words: 自定义敏感词(客户名/厂区名/设备名), 全匹配时整体掩码。
    mapping: {占位符: 原始敏感信息}
    """
    if not text:
        return text, {}
    mapping = {}
    counter = {"IP": 0, "PHONE": 0, "TEL": 0, "EMAIL": 0,
               "AMOUNT": 0, "ID": 0, "DOMAIN": 0, "SERIAL": 0,
               "WORD": 0}
    masked = text

    # 1. 自定义词(客户名/厂区名/设备名)优先(可能含中文, 独立处理)
    if custom_words:
        for w in custom_words:
            if w and w in masked:
                counter["WORD"] += 1
                ph = f"{{{{WORD_{counter['WORD']}}}}}"
                mapping[ph] = w
                masked = masked.replace(w, ph)

    # 2. 规则敏感信息
    for name, pat in RULES:
        def _sub(m, _name=name, _cnt=counter):
            token = m.group(0)
            counter[_name] += 1
            ph = f"{{{{{_name}_{counter[_name]}}}}}"
            mapping[ph] = token
            return ph
        masked = pat.sub(_sub, masked)

    return masked, mapping


def restore(text: str, mapping: dict) -> str:
    """按映射还原占位符为原始敏感信息。"""
    if not mapping or not text:
        return text
    out = text
    # 长占位符先还原(避免部分匹配)
    for ph in sorted(mapping.keys(), key=len, reverse=True):
        out = out.replace(ph, mapping[ph])
    return out


def mask_and_rewrite(text: str, style: str = "tweet", provider=None,
                     custom_words: list = None) -> dict:
    """一站式: 脱敏 → LLM改写 → 还原。

    写作文本先脱敏(掩码敏感信息), 交给 provider 改写(本地), 再还原。
    provider 为 None 时返回风格指导(同 writing.rewrite)。
    返回含 masked/rewritten/restored 字段, 便于审计脱敏前后。
    """
    from solo import writing
    masked, mapping = mask(text, custom_words)
    # 用脱敏后文本改写
    r = writing.rewrite(masked, style, provider)
    rewritten = r.get("rewritten", "")
    restored = restore(rewritten, mapping) if rewritten else ""
    return {
        "style": style,
        "masked_sensitive": len(mapping),   # 脱敏的敏感信息条数
        "mapping_count": len(mapping),
        "masked_text": masked,              # 脱敏后原文(审计用)
        "rewritten": rewritten,             # LLM改写结果(仍含占位符)
        "restored": restored,               # 还原后的最终文本
        "hint": r.get("hint"), "rules": r.get("rules"),
    }
