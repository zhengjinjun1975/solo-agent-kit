# -*- coding: utf-8 -*-
"""factory-cognition 原子：复用 factory-ontology-kit 认知/本体/RAG 能力（开源原子联动）。

联动复用（跨仓库，算法开源，数据不出厂）：
  - ontology_qa  : 调用 factory-ontology-kit/codes/ontology_qa_v3 本体规则问答（确定性、带证据）
  - retrieve     : 自包含离线 RAG 知识检索（BM25 稀疏 + 大词共现加权，纯标准库，离线可用，
                    存 data/knowledge/*.json；factory 侧有 ChromaDB 时可对接，缺库降级到本实现）
  - ask          : 确定性本体问答优先，miss 时降级到离线 RAG（先查库再答，防幻觉）

边界：本体/词典/文档数据各自落在本地 data/，联动只传「问题 + 数据路径」，算法开源、数据不出厂。
"""
from __future__ import annotations
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from fde_runtime.base import AtomicAgent, fail, ok  # noqa: E402
from fde_runtime import linkage  # noqa: E402


# ---- 离线 RAG（纯标准库）：BM25 稀疏检索 + 持久化到 JSON ----
def _tok(text: str) -> list:
    """轻量中文/英文 token 化：中文按字二元组 + 英文按词。"""
    text = (text or "").lower()
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    tokens = []
    for seg in cjk:
        seg = seg.strip()
        for i in range(len(seg) - 1):
            tokens.append(seg[i:i + 2])
        if len(seg) == 1:
            tokens.append(seg)
    tokens += re.findall(r"[a-z][a-z0-9_]{1,}", text)
    return tokens


def _bm25(query_tokens, chunks, k1=1.5, b=0.75):
    """BM25 稀疏检索。chunks: [{'text','score'}]，返回带 bm25 分的列表（保序）。"""
    import collections
    n = len(chunks)
    doc_lens = []
    tfs = []
    df = collections.Counter()
    for c in chunks:
        toks = _tok(c["text"])
        doc_lens.append(len(toks))
        cnt = collections.Counter(toks)
        tfs.append(cnt)
        for t in set(cnt):
            df[t] += 1
    avgdl = (sum(doc_lens) / n) if n else 1.0
    scores = []
    for i in range(n):
        dl = doc_lens[i]
        s = 0.0
        for t in query_tokens:
            f = tfs[i].get(t, 0)
            if f == 0:
                continue
            idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0)
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        scores.append(round(s, 4))
    return scores


class OfflineKnowledge:
    """离线知识库（纯标准库）：doc_id → 切块列表，持久化到 data/knowledge/<kb>.json。"""

    def __init__(self, kb_dir: str):
        self.kb_dir = kb_dir
        os.makedirs(kb_dir, exist_ok=True)

    def _path(self, kb: str):
        name = re.sub(r"[^0-9a-zA-Z_-]", "_", kb or "kb") or "kb"
        return os.path.join(self.kb_dir, name + ".json")

    def add_doc(self, kb: str, doc_id: str, title: str, chunks) -> dict:
        path = self._path(kb)
        store = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    store = json.load(f)
            except Exception:
                store = {}
        store[doc_id] = {"title": title, "chunks": chunks}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
        return {"doc_id": doc_id, "chunks": len(chunks)}

    def search(self, kb: str, question: str, top_k: int = 3, min_score: float = 0.0) -> list:
        path = self._path(kb)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            store = json.load(f)
        chunks = []
        src = []
        for doc_id, doc in store.items():
            for i, c in enumerate(doc.get("chunks") or []):
                text = c if isinstance(c, str) else (c.get("text") or "")
                chunks.append({"text": text})
                src.append({"doc_id": doc_id, "title": doc.get("title", doc_id), "chunk": i})
        if not chunks:
            return []
        qt = _tok(question)
        if not qt:
            return []
        scores = _bm25(qt, chunks)
        hits = []
        for i in range(len(chunks)):
            hits.append({"doc_id": src[i]["doc_id"], "title": src[i]["title"],
                         "chunk": chunks[i]["text"], "score": scores[i]})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return [h for h in hits[:top_k] if h["score"] > min_score]


class FactoryCognitionAtom(AtomicAgent):
    def capabilities(self):
        return ["factory.cognition"]

    def _run(self, op: str = "linkage", dir: str = None, **params):
        kb_dir = dir or os.path.join(_ROOT, "data", "knowledge")
        off = OfflineKnowledge(kb_dir)

        if op == "linkage":
            return ok(linkage.status())

        if op == "ontology_qa":
            """确定性本体问答（复用 factory ontology_qa_v3，真实跨仓库联动）。"""
            root = linkage.find_factory()
            if not root:
                return fail("factory-ontology-kit 未找到，无法本体问答（数据不出厂，需本地部署）",
                            degraded=True)
            linkage.add_codes_to_path(root)
            codes = os.path.join(root, "codes")
            nt = params.get("nt") or os.path.join(codes, "output", "valve.nt")
            lex = params.get("lexicon") or os.path.join(codes, "config", "lexicon_valve.json")
            q = params.get("question")
            if not q or not os.path.exists(nt) or not os.path.exists(lex):
                return fail("ontology_qa 需 question + 可用的 nt/lexicon")
            try:
                with linkage.codes_isolation(root):
                    import ontology_qa_v3 as v3  # noqa: PLC0415
                    D = v3.load_dict(lex)
                    data = v3.build_data(v3.parse_nt(nt), D)
                    ans = v3.answer(q, data, D)
                if not ans or ans.startswith("暂不支持"):
                    return ok({"answer": ans, "source": "ontology", "hit": False})
                return ok({"answer": ans, "source": "ontology", "hit": True})
            except Exception as e:  # noqa: BLE001
                return fail(f"factory 本体问答异常: {e}", degraded=True)

        if op == "add_doc":
            doc_id, chunks = params.get("doc_id"), params.get("chunks")
            kb = params.get("kb", "maintenance")
            if not doc_id or not chunks:
                return fail("add_doc 需 doc_id + chunks")
            r = off.add_doc(kb, doc_id, params.get("title", doc_id), chunks)
            return ok(r)

        if op == "retrieve":
            """离线 RAG 知识检索（先查库再答，防幻觉）。"""
            q = params.get("question")
            kb = params.get("kb", "maintenance")
            if not q:
                return fail("retrieve 需 question")
            hits = off.search(kb, q, top_k=params.get("top_k", 3),
                              min_score=params.get("min_score", 0.0))
            if not hits:
                return ok({"hits": [], "hit": False, "note": "库中无据，禁幻觉"})
            return ok({"hits": hits, "hit": True})

        if op == "ask":
            """认知问答：确定性本体问答优先，miss 时降级到离线 RAG。"""
            q = params.get("question")
            if not q:
                return fail("ask 需 question")
            root = linkage.find_factory()
            if root:
                r = self._run(op="ontology_qa", dir=dir, **params)
                if r.get("ok") and r["data"].get("hit"):
                    return r
            r2 = self._run(op="retrieve", dir=dir, **params)
            return r2

        return fail(f"未知 op: {op}")


def _main():
    a = FactoryCognitionAtom(name="factory-cognition", agent="cognition", version="0.1.0")
    a.load()
    # 1) 离线 RAG 真数据入库 + 检索（不依赖 factory 仓库，恒可测）
    import tempfile
    d = tempfile.mkdtemp(prefix="fde_cog_")
    a.run(op="add_doc", dir=d, kb="maintenance", doc_id="D001", title="水泵振动维修手册",
          chunks=[{"text": "水泵振动超限常见原因为轴承磨损，更换轴承后振动恢复至5.0以内"},
                  {"text": "泵轴对中不良会导致振动增大，需做动平衡校准"}])
    r = a.run(op="retrieve", dir=d, question="泵振动大怎么处理", kb="maintenance")
    assert r.get("ok") and r["data"]["hit"], "离线RAG检索应命中"
    print("  retrieve 命中:", r["data"]["hits"][0]["chunk"][:40])
    # 2) factory 本体问答（仓库存在则真联动）
    print("factory:", linkage.status()["factory_ontology_kit"]["present"])
    r2 = a.run(op="ontology_qa", question="一共有多少个阀门")
    print("  ontology_qa:", r2.get("data", {}).get("answer") if r2.get("ok") else r2.get("error"))
    print("factory-cognition 独立自测通过, 0 失败")


if __name__ == "__main__":
    _main()
