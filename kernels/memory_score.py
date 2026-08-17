# -*- coding: utf-8 -*-
"""kernels/memory_score.py — 记忆检索打分 纯函数内核。

迁移自 solo/memory.py 的纯函数：_overlap/_cosine/_hash/_is_noise/_consolidate 逻辑，
加上 CJK 分词 + 语义/词重叠/余弦检索打分。无状态、确定性。
消费原子：memory、ontology-qa、diagnose-kb。
"""
from __future__ import annotations

import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fa5]")


def tokenize(text: str) -> list:
    """中英混合分词：英文单词/数字 + 单个汉字（避免 \\w 一次性吞掉中文句）。"""
    return _TOKEN_RE.findall((text or "").lower())


def overlap(a: str, b: str) -> float:
    """字符 bigram 重叠率（零依赖语义打分）。"""
    a_b = {a[i:i + 2] for i in range(len(a) - 1)}
    b_b = {b[i:i + 2] for i in range(len(b) - 1)}
    if not b_b:
        return 0.0
    return len(a_b & b_b) / len(b_b)


def cosine(a: list, b: list) -> float:
    """余弦相似度（embed 向量检索）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def is_noise(text: str) -> bool:
    """过滤无沉淀价值的噪音（占位/问候/过短）。"""
    t = (text or "").strip()
    if len(t) < 6:
        return True
    low = t.lower()
    if low in {"hello", "hi", "test", "测试", "你好", "您好", "你好吗",
               "我该如何使用", "web端验证记忆", "验证记忆"}:
        return True
    if len(t) < 12 and any(k in low for k in ("测试", "临时", "验证", "placeholder")):
        return True
    return False


def semantic_score(query: str, text: str, use_token: bool = True) -> float:
    """语义检索打分（0~1）：词重叠（bigram）+ token 交集 加权。"""
    return round(0.7 * overlap(query, text) + 0.3 * _token_jaccard(query, text), 4)


def _token_jaccard(a: str, b: str) -> float:
    ta = set(tokenize(a))
    tb = set(tokenize(b))
    if not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


def rank_texts(query: str, texts: list, top_k: int = 5) -> list:
    """给候选文本打分并返回 top_k：[{text, score, index}, ...]（按 score 降序）。"""
    scored = [{"text": t, "score": semantic_score(query, t),
               "index": i} for i, t in enumerate(texts)]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def decide_write_action(similar: list, threshold: float = 0.6) -> dict:
    """记忆写入决策：相似召回 → ADD/UPDATE/SKIP（对齐 Mem0 决策循环）。"""
    if not similar:
        return {"action": "ADD", "reason": "无相似旧记忆，新增事实"}
    top_sim = similar[0][0]
    if top_sim >= 0.9:
        return {"action": "SKIP", "reason": "与现有记忆等价(相似度≥0.9)，跳过防重复"}
    if top_sim >= threshold:
        return {"action": "UPDATE", "reason": f"同主题记忆存在(相似度{top_sim:.2f})，更新而非重复新增"}
    return {"action": "ADD", "reason": "与现有记忆差异较大，新增事实"}
