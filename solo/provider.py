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
    """本地/云端模型的分层抽象（零依赖，标准库 urllib）。

    用法：
        p = Provider.from_config(config)     # 读 config dict（支持新旧两种格式）
        p = Provider.from_file()             # 读 config/model_config.json 或 provider.yaml（推荐）
        text = p.complete("轻量任务", tier="auto")  # auto 按 routing 智能路由
        text = p.complete("复杂任务", tier="remote") # 强制云端
        vec = p.embed("文本")                 # 嵌入（本地）

    新格式 config/model_config.json（仿工厂本体风格）：
        {"active","routing","embedding","models":{local,cloud}}。
    旧格式 provider.yaml 仍兼容，找不到新 JSON 时回退读取。
    """

    # 复杂任务关键词：命中即升云端（与 routing 的 complex_models 语义一致）
    COMPLEX_KEYWORDS = ("本体", "建模", "重构", "架构", "代码生成", "长文",
                        "报告", "写一篇", "深度分析", "方案", "复盘", "论文")

    def __init__(self, local=None, remote=None, embed=None, active=None, routing=None):
        self.local = local or {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest"}
        self.remote = remote or {}
        # 注意: 不能叫 self.embed——会遮蔽同名方法 embed()。配置用 embed_cfg。
        self.embed_cfg = embed or {"type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text:latest"}
        # 工厂本体风格：active 默认路由开关 + routing 智能路由策略
        self.active = active or "cloud"
        self.routing = routing or {}

    @classmethod
    def from_config(cls, config: dict) -> "Provider":
        """从 config dict 构造。支持两种格式：

        旧格式（provider.yaml 解析结果）：{"provider": {"local":..., "remote":..., "embed":...}}
        新格式（config/model_config.json）：{"active", "routing", "embedding", "models": {"local","cloud"}}
        """
        # 新格式：仿工厂本体 —— active/routing/embedding/models
        if "models" in config and isinstance(config.get("models"), dict):
            models = config["models"]
            local = dict(models.get("local") or {})
            cloud = dict(models.get("cloud") or {})
            # api_key 空值清理：留空则后续走环境变量 DEEPSEEK_API_KEY
            local = {k: v for k, v in local.items() if v != ""}
            cloud = {k: v for k, v in cloud.items() if v != ""}
            return cls(
                local=local,
                remote=cloud,
                embed=dict(config.get("embedding") or {}),
                active=config.get("active", "cloud"),
                routing=config.get("routing") or {},
            )
        # 旧格式：provider.yaml 形状
        p = config.get("provider", {})
        return cls(
            local=p.get("local", {}),
            remote=p.get("remote", {}),
            embed=p.get("embed", {}),
        )

    @classmethod
    def from_file(cls, path: str = None) -> "Provider":
        """从配置文件构造。path 缺省自动探测：

        1) config/model_config.json（新，仿工厂本体风格，含 active/routing）
        2) ./provider.yaml 或 ~/.solo/provider.yaml（旧，兼容）

        找不到返回默认（本地 ollama）。
        """
        mc = load_model_config(path)
        if mc:
            return cls.from_config(mc)  # 新格式：保留 active/routing 智能路由
        config = load_config(path)
        return cls.from_config(config or {})

    def complete(self, prompt: str, tier: str = "auto") -> str:
        """生成文本。tier: local / remote / auto。

        auto = 按 routing 智能路由（simple→local，complex→cloud）。
        云端不可用时降级本地；本地不可用时明确报错（不静默）。
        """
        cfg = self._pick(prompt, tier)
        if cfg.get("type") == "ollama":
            return self._ollama_generate(cfg, prompt)
        # 云端 = OpenAI 兼容端点；网络/服务不可用时降级本地，认证缺失(无 key)不降级(模型闭环铁律)
        try:
            return self._remote_generate(cfg, prompt)
        except ProviderError as e:
            if e.code == EXIT_AUTH:
                raise  # 云端无 key/认证失败：明确报错，不静默降级
            if self.local:
                return self._ollama_generate(self.local, prompt)
            raise

    def embed(self, text: str) -> list:
        """文本嵌入向量（本地，记忆不泄露）。"""
        cfg = self.embed_cfg
        if cfg.get("type") == "ollama":
            return self._ollama_embed(cfg, text)
        raise ProviderError("嵌入仅支持本地 ollama", EXIT_USER_ERR)

    # ---- 内部：分层选择（智能路由）----
    def _pick(self, prompt: str, tier: str) -> dict:
        """按 tier 与 routing 选模型层。

        - local  → 强制本地
        - remote → 强制云端（无则降级本地）
        - auto   → routing：active=local 恒走本地；否则 simple→local，
                   complex（长 prompt 或含复杂关键词）→ cloud，云端无则本地。
        """
        if tier == "local":
            return self.local
        if tier == "remote":
            return self.remote or self.local
        # auto：启用工厂本体风格 routing
        if self.routing:
            if self.active == "local":
                return self.local
            if self.remote and self._is_complex(prompt):
                return self.remote
            return self.local
        # 旧启发式兜底：长 prompt 或含复杂任务词 → 云端
        if self.remote and self._is_complex(prompt):
            return self.remote
        return self.local

    def _is_complex(self, prompt: str) -> bool:
        """判断任务是否复杂（simple→local / complex→cloud）。"""
        return len(prompt) > 2000 or any(w in prompt for w in self.COMPLEX_KEYWORDS)

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

    # ---- 云端 OpenAI 兼容 ----
    def _remote_generate(self, cfg, prompt: str) -> str:
        url = cfg.get("base_url", "").rstrip("/") + "/chat/completions"
        # key 优先级：config 内 api_key 字段 > 环境变量 api_key_env > 兜底读 .env
        env_name = cfg.get("api_key_env", "DEEPSEEK_API_KEY")
        api_key = resolve_remote_key(cfg)
        if not api_key:
            # 模型闭环铁律：云端无 key 明确报错，不静默降级
            raise ProviderError(
                "云端模型未配置 API key（设环境变量 %s，或在 config/model_config.json 填 api_key）" % env_name,
                EXIT_AUTH)
        payload = {"model": cfg.get("model"), "messages": [{"role": "user", "content": prompt}]}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ProviderError("云端认证失败（API key 无效）", EXIT_AUTH)
            raise ProviderError(f"云端请求失败 HTTP {e.code}", EXIT_NETWORK)
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ProviderError(f"云端不可用（{reason}）", EXIT_NETWORK)


def resolve_remote_key(remote_cfg: dict) -> str:
    """解析云端模型可用 key：配置内 api_key 字段 > 环境变量 api_key_env > 兜底读 .env。

    同时兼容新格式 model_config.json（api_key 字段）与旧格式 provider.yaml（api_key_env）。
    """
    env_name = remote_cfg.get("api_key_env", "DEEPSEEK_API_KEY")
    return (remote_cfg.get("api_key", "") or
            os.environ.get(env_name, "") or _read_env_key(env_name))


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


def _find_config_file(path: str = None) -> str:
    """定位配置文件。显式 path 优先；缺省按新→旧顺序探测：

    1) config/model_config.json（新，仿工厂本体风格）
    2) ./provider.yaml
    3) ~/.solo/provider.yaml（旧，兼容）

    找不到返回 None。
    """
    if path:
        return path if os.path.exists(path) else None
    for cand in ("config/model_config.json",
                 "provider.yaml",
                 os.path.join(os.path.expanduser("~"), ".solo", "provider.yaml")):
        if os.path.exists(cand):
            return cand
    return None


def load_model_config(path: str = None) -> dict:
    """读取 config/model_config.json（工厂本体风格）为 dict。

    返回 {"active","routing","embedding","models":{local,cloud}}；
    找不到（或非 json）返回空 dict。
    """
    p = _find_config_file(path)
    if not p or not p.endswith(".json"):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _json_to_provider_shape(mc: dict) -> dict:
    """把新格式 model_config.json 归一化为旧 provider.yaml 形状（供既有调用点兼容）。"""
    models = mc.get("models", {})

    def _norm(m):
        return {k: m[k] for k in ("type", "base_url", "model") if k in m}

    return {
        "provider": {
            "local": _norm(models.get("local") or {}),
            "remote": _norm(models.get("cloud") or {}),
            "embed": _norm(mc.get("embedding") or {}),
        }
    }


def model_config_payload(path: str = None) -> dict:
    """返回仿工厂本体的前端可编辑配置（扁平 + api_key 脱敏）。

    结构：{configured, active, models:[{key,name,type,base_url,model,has_key,api_key_status}],
           embedding, routing, local, remote, embed}
    - models 为模型列表（每项含 key）；api_key 不泄露原文，用 has_key/api_key_status 占位，
      前端输入新值时后端保留原值。
    - 优先读新格式 config/model_config.json；回退旧 provider.yaml（active 取 remote）。
    - local/remote/embed 为旧字段兜底，供聊天摘要 fmtResult('config') 复用。
    """
    mc = load_model_config(path)
    if mc and isinstance(mc.get("models"), dict):
        models = []
        for key, m in (mc.get("models") or {}).items():
            has = bool(m.get("api_key"))
            models.append({
                "key": key,
                "name": m.get("name") or key,
                "type": m.get("type") or "ollama",
                "base_url": m.get("base_url") or "",
                "model": m.get("model") or "",
                "has_key": has,
                "api_key_status": "已配置" if has else "",
            })
        emb = dict(mc.get("embedding") or {})
        return {
            "configured": True,
            "active": mc.get("active") or "",
            "active_model": mc.get("active") or "",
            "models": models,
            "embedding": emb,
            "routing": mc.get("routing") or {},
            "local": {"type": (mc.get("models", {}).get("local") or {}).get("type", "ollama"),
                      "model": (mc.get("models", {}).get("local") or {}).get("model", "")},
            "remote": {"type": (mc.get("models", {}).get("cloud") or {}).get("type", ""),
                       "model": (mc.get("models", {}).get("cloud") or {}).get("model", "")},
            "embed": {"model": (mc.get("embedding") or {}).get("model", "")},
        }
    # 旧 provider.yaml 回退：local/remote/embed → 扁平模型列表
    cfg = load_config(path)
    p = cfg.get("provider", {})
    local = p.get("local") or {}
    remote = p.get("remote") or {}
    embed = p.get("embed") or {}
    remote_has = bool(resolve_remote_key(remote))
    models = [
        {"key": "local", "name": "本地模型", "type": local.get("type", "ollama"),
         "base_url": local.get("base_url", ""), "model": local.get("model", ""),
         "has_key": False, "api_key_status": ""},
        {"key": "cloud", "name": "云端模型", "type": remote.get("type", "openai"),
         "base_url": remote.get("base_url", ""), "model": remote.get("model", ""),
         "has_key": remote_has, "api_key_status": "已配置" if remote_has else ""},
    ]
    return {
        "configured": bool(p),
        "active": "remote" if remote else "local",
        "active_model": "remote" if remote else "local",
        "models": models,
        "embedding": {"type": embed.get("type", "ollama"), "base_url": embed.get("base_url", "http://127.0.0.1:11434"),
                      "model": embed.get("model", "nomic-embed-text")},
        "routing": {},
        "local": {"type": local.get("type", "ollama"), "model": local.get("model", "")},
        "remote": {"type": remote.get("type", ""), "model": remote.get("model", "")},
        "embed": {"model": embed.get("model", "")},
    }


def save_model_config(payload: dict, path: str = None) -> dict:
    """把前端编辑结果写回 config/model_config.json（新格式，仿工厂本体）。

    payload: {active, models:[{key,name,type,base_url,model,api_key}], embedding}
    - models 列表按 key 合并进 models dict；api_key 留空 = 保留原值，仅输入新值才更新。
    - active/embedding 一并更新；保留 routing 与 _comment 等既有字段。
    返回 {ok, active}（失败时 {ok:False, error}）。
    """
    mc = load_model_config(path)
    if not isinstance(mc, dict):
        mc = {}
    # 目标路径：显式 path，否则优先写新格式 config/model_config.json
    if not path:
        p = _find_config_file(None)
        path = p if (p and p.endswith(".json")) else "config/model_config.json"
    models = dict(mc.get("models") or {})
    for m in (payload.get("models") or []):
        key = m.get("key", "")
        if not key:
            continue
        entry = dict(models.get(key) or {})
        entry["name"] = m.get("name", entry.get("name", key))
        entry["type"] = m.get("type", entry.get("type", "ollama"))
        entry["base_url"] = m.get("base_url", entry.get("base_url", ""))
        entry["model"] = m.get("model", entry.get("model", ""))
        if m.get("api_key"):  # 留空 = 保留原值，仅输入新值才更新
            entry["api_key"] = m["api_key"]
        models[key] = entry
    mc["models"] = models
    if payload.get("active") in models:
        mc["active"] = payload["active"]
    elif not mc.get("active"):
        mc["active"] = next(iter(models), "")
    if payload.get("embedding") is not None:
        emb = payload["embedding"]
        old = mc.get("embedding") or {}
        mc["embedding"] = {
            "name": emb.get("name", old.get("name", "本地向量模型")),
            "type": emb.get("type", old.get("type", "ollama")),
            "base_url": emb.get("base_url", old.get("base_url", "http://127.0.0.1:11434")),
            "model": emb.get("model", old.get("model", "nomic-embed-text")),
            "api_key": emb.get("api_key", old.get("api_key", "")),
        }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(mc, f, ensure_ascii=False, indent=2)
        return {"ok": True, "active": mc.get("active", "")}
    except OSError:
        return {"ok": False, "error": "模型配置写入失败"}


def load_config(path: str = None) -> dict:
    """读取模型配置为 dict。优先新格式 config/model_config.json，找不到回退 provider.yaml。

    返回归一化为旧形状 {"provider": {local/remote/embed}}，
    使 agent/cli/web 等既有调用点无需改动即可兼容。
    """
    p = _find_config_file(path)
    if not p or not os.path.exists(p):
        return {}
    # 新格式：JSON → 归一化为 provider 形状
    if p.endswith(".json"):
        mc = load_model_config(p)
        return _json_to_provider_shape(mc) if mc else {}
    # 旧格式：零依赖极简 YAML 解析（按缩进层级）。
    # 支持：顶层键(provider) → 二级(local/remote/embed) → 三级(type/base_url/model/api_key_env)。
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()

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

    cfg = {}
    _parse_into(cfg, lines, 0, parent_indent=-1)
    return cfg
