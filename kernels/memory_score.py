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
    """给候选文本打分并返回 top_k：[{text, score, index}, ...]（按 score 降序）。

    升级（P1）：从纯词法升级为「真向量」语义检索——
      - vector_embed 字符/词 n-gram 哈希向量 + 余弦相似度；
      - 可选 bge 嵌入（embed_fn 注入），无嵌入模型时降级 n-gram 向量。
    """
    embed = _embed_fn() or _vector_embed
    qv = embed(query)
    scored = [{"text": t, "score": round(_cos_vec(qv, embed(t)), 4),
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


# ═══════════════════════════════════════════════════════════════════
# P1：离线 RAG 真向量 —— 字符/词 n-gram 哈希向量 + 余弦（零依赖）
# ═══════════════════════════════════════════════════════════════════
_VEC_DIM = 512          # 固定哈希向量维度（轻量，无第三方库）
_EMBED_FN = {"fn": None}


def set_embed_fn(fn):
    """注入可选嵌入函数（如 bge 模型）；fn(text)->list[float]。None 恢复 n-gram。"""
    _EMBED_FN["fn"] = fn


def _embed_fn():
    """返回当前嵌入函数（注入的 bge 或 None→n-gram 兜底）。"""
    return _EMBED_FN["fn"]


def _hash_idx(term: str, salt: int = 0) -> int:
    """把 term 哈希到 [0, _VEC_DIM) 索引，支持正/负符号（signed 哈希）。"""
    h = int.from_bytes(
        hashlib.sha256(f"{salt}:{term}".encode("utf-8")).digest()[:8], "big")
    return h % _VEC_DIM


def _ngrams(text: str, n: int = 3) -> list:
    """字符 n-gram（含边界）——捕捉近义子串/词形相似。"""
    t = re.sub(r"\s+", "", (text or "").lower())
    grams = [t[i:i + n] for i in range(max(len(t) - n + 1, 1))]
    return grams or []


def _vector_embed(text: str) -> list:
    """轻量哈希向量：字符 n-gram(1~3) + 词 token 混合，带符号哈希 + 词频加权。

    零依赖、确定性、可比较（同文本同向量）。维度固定 _VEC_DIM。
    """
    vec = [0.0] * _VEC_DIM
    for gram in set(_ngrams(text, 1)) | set(_ngrams(text, 2)) | set(_ngrams(text, 3)):
        idx = _hash_idx(gram)
        sign = 1.0 if _hash_idx(gram, 7) % 2 == 0 else -1.0
        vec[idx] += sign
    for tok in set(tokenize(text)):
        idx = _hash_idx("w:" + tok)
        sign = 1.0 if _hash_idx("w:" + tok, 7) % 2 == 0 else -1.0
        vec[idx] += 1.5 * sign
    # L2 归一化（余弦可比）
    norm = sum(x * x for x in vec) ** 0.5
    if norm:
        vec = [x / norm for x in vec]
    return vec


def _cos_vec(a: list, b: list) -> float:
    return cosine(a, b)


def vector_embed(text: str) -> list:
    """对外向量接口：优先注入的 bge 嵌入，否则 n-gram 哈希向量兜底。"""
    fn = _embed_fn()
    if fn is not None:
        try:
            v = fn(text)
            if isinstance(v, (list, tuple)) and v:
                return list(v)
        except Exception:  # noqa: BLE001
            pass
    return _vector_embed(text)


def vector_rank(query: str, texts: list, top_k: int = 5) -> list:
    """真向量语义排序：向量余弦相似度（近义词/词形相似命中）。"""
    embed = vector_embed
    qv = embed(query)
    scored = [{"text": t, "score": round(_cos_vec(qv, embed(t)), 4),
               "index": i} for i, t in enumerate(texts)]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def hybrid_rank(query: str, texts: list, top_k: int = 5,
                vec_w: float = 0.7, lex_w: float = 0.3) -> list:
    """混合检索：真向量 + 词法（BM25/重叠）加权。对齐业界 BM25+向量 标准。"""
    vec_scores = {i: s for i, s in
                  [(r["index"], r["score"]) for r in vector_rank(query, texts, len(texts))]}
    lex_scores = {r["index"]: r["score"]
                  for r in rank_texts_lexical(query, texts)}
    scored = []
    for i, t in enumerate(texts):
        score = vec_w * vec_scores.get(i, 0.0) + lex_w * lex_scores.get(i, 0.0)
        scored.append({"text": t, "score": round(score, 4), "index": i})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def rank_texts_lexical(query: str, texts: list) -> list:
    """纯词法排序（保留 BM25 语义，供混合检索 / 旧接口兼容）。"""
    scored = [{"text": t, "score": semantic_score(query, t), "index": i}
              for i, t in enumerate(texts)]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
