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
        p = Provider.from_file()           # 从 provider.yaml 读（推荐）
        text = p.complete("轻量任务", tier="local")     # 本地
        text = p.complete("复杂任务", tier="remote")    # 远端
        vec = p.embed("文本")                            # 嵌入（本地）
    """

    def __init__(self, local=None, remote=None, embed=None):
        self.local = local or {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest"}
        self.remote = remote or {}
        # 注意: 不能叫 self.embed——会遮蔽同名方法 embed()。配置用 embed_cfg。
        self.embed_cfg = embed or {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text:latest"}

    @classmethod
    def from_config(cls, config: dict) -> "Provider":
        """从 config dict 构造。config 通常来自 provider.yaml。"""
        p = config.get("provider", {})
        return cls(
            local=p.get("local", {}),
            remote=p.get("remote", {}),
            embed=p.get("embed", {}),
        )

    @classmethod
    def from_file(cls, path: str = None) -> "Provider":
        """从 provider.yaml 文件构造。path 缺省找 ./provider.yaml 或 ~/.solo/provider.yaml。

        零依赖解析（极简缩进 yaml 子集），找不到返回默认（本地 ollama）。
        """
        config = load_config(path)
        return cls.from_config(config or {})

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
        cfg = self.embed_cfg
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
        url = cfg.get("base_url", "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
        payload = {"model": cfg.get("model"), "prompt": prompt, "stream": False}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r).get("response", "")
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ProviderError(f"本地模型不可用（{reason}）", EXIT_NETWORK)

    def _ollama_embed(self, cfg, text: str) -> list:
        url = cfg.get("base_url", "http://127.0.0.1:11434").rstrip("/") + "/api/embeddings"
        payload = {"model": cfg.get("model"), "prompt": text}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("embedding", [])
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ProviderError(f"嵌入模型不可用（{reason}）", EXIT_NETWORK)

    # ---- 远端 OpenAI 兼容 ----
    def _remote_generate(self, cfg, prompt: str) -> str:
        url = cfg.get("base_url", "").rstrip("/") + "/chat/completions"
        api_key = os.environ.get(cfg.get("api_key_env", "DEEPSEEK_API_KEY"), "") or \
            _read_env_key(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
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
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ProviderError(f"远端不可用（{reason}）", EXIT_NETWORK)


def _read_env_key(key: str) -> str:
    """从 ~/.env 文件读取密钥（web 服务等进程未 source .env 时兜底）。"""
    for p in [os.path.expanduser("~/.env"),
              os.path.join(os.getcwd(), ".env")]:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.startswith(key):
                        return line.split("=", 1)[1].strip()
        except OSError:
            continue
    return ""


def load_config(path: str = None) -> dict:
    """读取 provider.yaml 为 dict。零依赖极简 YAML 解析（按缩进层级）。

    支持：顶层键(provider) → 二级(local/remote/embed) → 三级(type/base_url/model/api_key_env)。
    找文件顺序：显式 path → ./provider.yaml → ~/.solo/provider.yaml
    找不到返回空 dict。
    """
    if path is None:
        candidates = ["provider.yaml",
                      os.path.join(os.path.expanduser("~"), ".solo", "provider.yaml")]
        path = next((p for p in candidates if os.path.exists(p)), None)
    if not path or not os.path.exists(path):
        return {}

    def _parse_into(node, lines, idx, parent_indent=-1):
        while idx < len(lines):
            raw = lines[idx]
            line = raw.rstrip("\n")
            if not line.strip() or line.strip().startswith("#"):
                idx += 1
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent <= parent_indent:
                break
            key, _, val = line.strip().partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                node[key] = val.strip('"').strip("'")
                idx += 1
            else:
                child = {}
                node[key] = child
                idx = _parse_into(child, lines, idx + 1, indent)
        return idx

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    cfg = {}
    _parse_into(cfg, lines, 0, parent_indent=-1)
    return cfg
