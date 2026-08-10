# -*- coding: utf-8 -*-
"""语义检索显式测试（补 provider.embed 遮蔽 bug 的盲区）。

背景：Provider.embed() 方法曾被 self.embed 实例属性遮蔽，导致 p.embed() 调用
必然抛 'dict' object is not callable，语义检索每次被 _try_embed 的 try/except
吞掉回退到词重叠——功能不崩但"语义检索"从未真正生效，且 37 项旧测试全绿（无覆盖）。

本文件专门验证：
1. Provider.embed() 是 method（不被属性遮蔽），且能产出向量
2. memory.search(semantic=True) 在 embed 可用时按余弦相似度正确排序
3. embed 不可用（本地 Ollama 不在）时静默回退词重叠，不崩溃

用 monkeypatch 注入确定性 embed，保证 CI 无 Ollama 也能跑且结果确定。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import memory as memory_mod
from solo import provider as provider_mod


# ---- 1. Provider.embed() 方法遮蔽回归 ----
def test_provider_embed_is_method_not_shadowed():
    """Provider.embed 必须是方法（不能被 self.embed 属性遮蔽）。"""
    p = provider_mod.Provider()
    # 关键回归: embed 应是 method, 不是 dict (曾因 self.embed 遮蔽成 dict)
    assert callable(p.embed), "embed 必须是可调用的方法(不能被实例属性遮蔽)"
    assert isinstance(p.embed, type(p.complete)), "embed 应和 complete 一样是 method"
    # 配置存在独立属性
    assert isinstance(p.embed_cfg, dict), "embed 配置应在 embed_cfg (不被方法名占用)"


def test_provider_embed_returns_vector_with_mock_backend(monkeypatch):
    """mock 本地端点, 验证 embed() 产出向量(不依赖真实 Ollama)。"""
    p = provider_mod.Provider()
    # 替换内部网络调用为确定返回值
    monkeypatch.setattr(provider_mod.Provider, "_ollama_embed",
                        lambda self, cfg, text: [0.1, 0.2, 0.3])
    vec = p.embed("测试文本")
    assert isinstance(vec, list)
    assert len(vec) == 3
    assert all(isinstance(x, (int, float)) for x in vec)


# ---- 2. 语义检索排序（核心盲区）----
def _mock_embed_dim(self, text):
    """确定性伪向量: 按文本哈希生成 8 维向量, 相同文本向量相同。
    让语义检索可测试且确定——查询向量与目标事实向量的余弦可算。"""
    import hashlib
    h = hashlib.md5(text.encode("utf-8")).digest()
    # 从哈希生成 8 个浮点, 归一化不必要(cosine 自动)
    return [b / 255.0 - 0.5 for b in h[:8]]


def test_semantic_search_ranks_by_cosine(monkeypatch, tmp_path):
    """semantic=True 且 embed 可用时, 按余弦相似度降序排序。"""
    m = memory_mod.Memory(mem_dir=os.path.join(tmp_path, "mem"))
    # 注入确定 embed(作用于类方法, mock 需接受 self)
    monkeypatch.setattr(memory_mod.Memory, "_try_embed", _mock_embed_dim)
    m.add_fact("本体建模用于工厂数据问答", ["本体"])
    m.add_fact("GitHub凭证已配置", ["github"])
    m.add_fact("用户偏好中文沟通", ["偏好"])

    # 查询"本体" → 应"本体建模"排最前
    res = m.search("本体", top_k=3, semantic=True)
    assert res, "应有检索结果"
    assert "本体" in res[0]["text"], "语义检索应把语义最相关的事实排第一"
    # 本体相关排在 GitHub 之前
    assert "GitHub" not in res[0]["text"]


def test_semantic_search_falls_back_when_embed_unavailable(monkeypatch, tmp_path):
    """embed 不可用(如无 Ollama)时, 静默回退词重叠, 不崩溃。"""
    m = memory_mod.Memory(mem_dir=os.path.join(tmp_path, "mem"))
    # embed 返回 None(模拟本地模型不可用)
    monkeypatch.setattr(memory_mod.Memory, "_try_embed", lambda self, text: None)
    m.add_fact("本体建模用于工厂数据问答", ["本体"])
    m.add_fact("GitHub凭证已配置", ["github"])

    res = m.search("本体", top_k=2, semantic=True)
    assert res, "embed 不可用时应回退词重叠仍有结果"
    # 词重叠: 含"本体"的事实应排前
    assert "本体" in res[0]["text"]


def test_semantic_search_word_overlap_non_semantic(tmp_path):
    """semantic=False 时走词重叠, 不依赖 embed。"""
    m = memory_mod.Memory(mem_dir=os.path.join(tmp_path, "mem"))
    m.add_fact("本体建模用于工厂数据问答", ["本体"])
    m.add_fact("GitHub凭证已配置", ["github"])
    res = m.search("本体", top_k=2, semantic=False)
    assert res
    assert "本体" in res[0]["text"]


# ---- 3. 端到端: 真实 embed 路径(若本地 Ollama 在, 可选验证) ----
def test_embed_integration_skips_if_no_ollama():
    """若本地 Ollama 有嵌入模型, 验证真实 embed 端到端可用。
    无 Ollama 则跳过(不阻塞 CI)。"""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
            import json
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
    except Exception:
        import pytest
        pytest.skip("本地 Ollama 未运行, 跳过真实 embed 集成测试")
    embed_ok = any("embed" in m for m in models)
    if not embed_ok:
        import pytest
        pytest.skip("无嵌入模型, 跳过")
    p = provider_mod.Provider.from_file()
    vec = p.embed("语义检索集成验证")
    assert isinstance(vec, list) and len(vec) > 0
