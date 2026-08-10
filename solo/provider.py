# -*- coding: utf-8 -*-
"""provider.py — 模型分层抽象（本地 + 远端混合，零依赖）。

方法论：轻量推理走本地（快/免费/私有），复杂推理走远端（强），
嵌入走本地（记忆不泄露）。可替换、可降级、不硬编码。

调用 OpenAI 兼容端点用标准库 urllib，不引 requests。
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

# 退出码：对齐 buzz-cli 分级（见 VISION §12.5）
EXIT_OK = 0
EXIT_USER_ERR = 1
EXIT_NETWORK = 2
EXIT_AUTH = 3
EXIT_OTHER = 4
EXIT_WRITE_CONFLICT = 5


class ProviderError(Exception):
    """模型调用错误，带分级退出码。"""

    def __init__(self, message: str, code: int = EXIT_OTHER):
        super().__init__(message)
        self.code = code


class Provider:
    """本地/远端模型的分层抽象。

    用法：
        p = Provider.from_config(config)   # 读 config dict
        text = p.complete("轻量任务", tier="local")     # 本地
        text = p.complete("复杂任务", tier="remote")    # 远端
        vec = p.embed("文本")                            # 嵌入（本地）
    """

    def __init__(self, local=None, remote=None, embed=None):
        self.local = local or {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest"}
        self.remote = remote or {}
        self.embed = embed or {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text:latest"}

    @classmethod
    def from_config(cls, config: dict) -> "Provider":
        """从 config dict 构造。config 通常来自 provider.yaml。"""
        p = config.get("provider", {})
        return cls(
            local=p.get("local", {}),
            remote=p.get("remote", {}),
            embed=p.get("embed", {}),
        )

    def complete(self, prompt: str, tier: str = "auto") -> str:
        """生成文本。tier: local / remote / auto。

        auto = 由 prompt 长度和是否含复杂关键词启发式选层（轻量优先）。
        远端不可用时降级本地；本地不可用时明确报错（不静默）。
        """
        cfg = self._pick(prompt, tier)
        if cfg.get("type") == "ollama":
            return self._ollama_generate(cfg, prompt)
        # 远端 = OpenAI 兼容端点
        return self._remote_generate(cfg, prompt)

    def embed(self, text: str) -> list:
        """文本嵌入向量（本地，记忆不泄露）。"""
        cfg = self.embed
        if cfg.get("type") == "ollama":
            return self._ollama_embed(cfg, text)
        raise ProviderError("嵌入仅支持本地 ollama", EXIT_USER_ERR)

    # ---- 内部：分层选择 ----
    def _pick(self, prompt: str, tier: str) -> dict:
        if tier == "local":
            return self.local
        if tier == "remote":
            return self.remote or self.local
        # auto：启发式——长 prompt 或含复杂任务词 → 远端
        if self.remote:
            COMPLEX = ("本体", "建模", "重构", "架构", "代码生成", "长文", "报告")
            if len(prompt) > 2000 or any(w in prompt for w in COMPLEX):
                return self.remote
        return self.local

    # ---- 本地 Ollama ----
    def _ollama_generate(self, cfg, prompt: str) -> str:
        url = cfg["base_url"].rstrip("/") + "/api/generate"
        payload = {"model": cfg.get("model"), "prompt": prompt, "stream": False}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r).get("response", "")
        except urllib.error.URLError as e:
            # 远端已降级到本地仍失败 → 明确报错
            raise ProviderError(f"本地模型不可用（{e.reason}）", EXIT_NETWORK)

    def _ollama_embed(self, cfg, text: str) -> list:
        url = cfg["base_url"].rstrip("/") + "/api/embeddings"
        payload = {"model": cfg.get("model"), "prompt": text}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("embedding", [])
        except urllib.error.URLError as e:
            raise ProviderError(f"嵌入模型不可用（{e.reason}）", EXIT_NETWORK)

    # ---- 远端 OpenAI 兼容 ----
    def _remote_generate(self, cfg, prompt: str) -> str:
        url = cfg.get("base_url", "").rstrip("/") + "/chat/completions"
        api_key = os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "")
        if not api_key:
            # 模型闭环铁律：云端无 key 明确报错，不静默降级
            raise ProviderError("远端模型未配置 API key（设环境变量 %s）" % cfg.get("api_key_env"), EXIT_AUTH)
        payload = {"model": cfg.get("model"), "messages": [{"role": "user", "content": prompt}]}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ProviderError("远端认证失败（API key 无效）", EXIT_AUTH)
            raise ProviderError(f"远端请求失败 HTTP {e.code}", EXIT_NETWORK)
        except urllib.error.URLError as e:
            raise ProviderError(f"远端不可用（{e.reason}）", EXIT_NETWORK)
