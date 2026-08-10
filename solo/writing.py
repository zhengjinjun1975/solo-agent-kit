# -*- coding: utf-8 -*-
"""writing.py — 六维中文写作质量检查（D1-D6）。

方法论：正确性(fail必改) / 风格(warn建议，保活人感)。
六维：D1错字 / D2标点(fail) / D3语病(fail) / D4数字 / D5去AI味 / D6活人感。
复刻自 zh-writing-checker（方法论借鉴，标准库实现）。
"""
from __future__ import annotations

import re

VERSION = "1.0"

# D1 常见错别字对
TYPO = {"寒喧": "寒暄", "幅射": "辐射", "决窍": "诀窍", "松驰": "松弛",
        "挖墙角": "挖墙脚", "言简意骇": "言简意赅", "世外桃园": "世外桃源"}

# D2 标点（fail）：中英标点混用
PUNCT_ISSUES = [
    ("英文逗号,", r"[a-zA-Z0-9],\s"),
    ("英文句号.", r"[a-zA-Z0-9]\.\s"),
    ("英文分号;", r";"),
]

# D3 语病（fail）：成分残缺/搭配不当/句式杂糅/前后矛盾
GRAMMAR = [
    ("通过…使(成分残缺)", r"通过.{2,20}使"),
    ("改善…水平(搭配不当)", r"改善.{1,8}水平"),
    ("因为…原因(句式杂糅)", r"因为.{1,10}原因"),
    ("大约…左右(前后矛盾)", r"大约.{1,8}左右"),
    ("是否…能否(双重)", r"是否.{1,10}能否"),
]

# D5 去AI味：破折号/禁用词/元语言/教科书开头
AI_PATTERNS = [
    ("破折号", r"——"),
    ("禁用词-赋能", r"赋能"),
    ("禁用词-闭环", r"闭环"),
    ("禁用词-底层逻辑", r"底层逻辑"),
    ("元语言-总而言之", r"总而言之|综上所述"),
    ("元语言-值得注意的是", r"值得注意的是"),
]


def scan(text: str) -> dict:
    """六维扫描，返回结构化报告。text 为要检查的中文文本。"""
    issues = []
    dim_counts = {"D1": 0, "D2": 0, "D3": 0, "D4": 0, "D5": 0, "D6": 0}
    dim_status = {}

    # D1 错字（warn）
    for wrong, right in TYPO.items():
        if wrong in text:
            issues.append({"dim": "D1", "severity": "warn", "msg": f"错字/异形词: {wrong}→{right}"})
            dim_counts["D1"] += 1

    # D2 标点（fail）
    for name, pat in PUNCT_ISSUES:
        if re.search(pat, text):
            issues.append({"dim": "D2", "severity": "fail", "msg": f"标点: {name}"})
            dim_counts["D2"] += 1

    # D3 语病（fail）
    for name, pat in GRAMMAR:
        if re.search(pat, text):
            issues.append({"dim": "D3", "severity": "fail", "msg": f"语病: {name}"})
            dim_counts["D3"] += 1

    # D4 数字（warn）：中文数字与阿拉伯混排、范围连接号
    if re.search(r"[0-9]个|一[二三四五六七八九十百千]个", text):
        dim_counts["D4"] += 1
        issues.append({"dim": "D4", "severity": "warn", "msg": "数字: 中英数字混排"})

    # D5 去AI味（warn+fail）
    for name, pat in AI_PATTERNS:
        n = len(re.findall(pat, text))
        if n:
            sev = "fail" if name in ("破折号",) else "warn"
            issues.append({"dim": "D5", "severity": sev, "msg": f"去AI味: {name} ×{n}"})
            dim_counts["D5"] += n

    # D6 活人感（warn）：句长均匀性（无节奏）
    sents = [s for s in re.split(r"[。！？]", text) if s.strip()]
    if len(sents) >= 3:
        lens = [len(s) for s in sents]
        avg = sum(lens) / len(lens)
        variance = sum((l - avg) ** 2 for l in lens) / len(lens)
        if variance < 5:  # 句长过于均匀 = 无节奏
            dim_counts["D6"] += 1
            issues.append({"dim": "D6", "severity": "warn", "msg": "活人感: 句长过于均匀，缺节奏"})

    # 每维状态：fail维度则整维fail，否则warn
    for d in ("D1", "D2", "D3", "D4", "D5", "D6"):
        n = dim_counts[d]
        has_fail = any(i["dim"] == d and i["severity"] == "fail" for i in issues)
        dim_status[d] = "fail" if has_fail else ("warn" if n else "pass")

    fail_count = sum(1 for i in issues if i["severity"] == "fail")
    return {
        "version": VERSION,
        "total_issues": len(issues),
        "fail_count": fail_count,
        "passed": fail_count == 0,
        "dimension_counts": dim_counts,
        "dimension_status": dim_status,
        "issues": issues,
    }
