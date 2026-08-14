# SoloAgentKit 配置文档

> 模型配置：本地（Ollama）+ 云端（OpenAI 兼容）+ 嵌入。零依赖。
> 仿工厂本体开源风格，主配置为 **`config/model_config.json`**；旧版 `provider.yaml` 仍兼容。

## 配置文件位置（读取顺序）

1. `config/model_config.json`（新，推荐）
2. `./provider.yaml`（旧，兼容）
3. `~/.solo/provider.yaml`（旧，兼容）

## 新格式 `config/model_config.json`

```jsonc
{
  "_comment": "模型配置：local=本地ornith(Ollama,无需key)，cloud=云端DeepSeek(OpenAI兼容,需api_key)。api_key 留空则读环境变量 DEEPSEEK_API_KEY。",
  "active": "cloud",   // 默认路由开关：cloud / local
  "routing": {
    "policy": "simple->local ; complex->cloud ; offline->fallback local ; all-down->rule/retrieval",
    "complex_models": ["cloud", "local"],
    "simple_models": ["local"],
    "offline_fallback": true
  },
  "embedding": { "name": "本地向量模型", "type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text", "api_key": "" },
  "models": {
    "local": { "name": "本地 ornith", "type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest", "api_key": "" },
    "cloud": { "name": "云端 DeepSeek", "type": "openai", "base_url": "https://api.deepseek.com", "model": "deepseek-chat", "api_key": "" }
  }
}
```

## 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `active` | 否 | 默认路由开关。`cloud` = 复杂任务优先云端；`local` = 一律本地（离线/省钱），默认 `cloud` |
| `routing.simple_models` | 否 | 简单任务用层（默认 `local`） |
| `routing.complex_models` | 否 | 复杂任务优先层（默认 `cloud` → 回退 `local`） |
| `routing.offline_fallback` | 否 | 云端离线/无 key/HTTP 错是否降级本地 |
| `models.local` | 推荐 | 本地 ornith（Ollama，无需 key） |
| `models.cloud` | 可选 | 云端 DeepSeek，`api_key` 留空则读 `DEEPSEEK_API_KEY` |
| `embedding` | 可选 | 嵌入模型（记忆向量检索，本地） |

## 模型路由逻辑（agent 对话，tier=auto）

- 简单对话/短任务 → `local`（本地 ornith，快/免费/私有）
- 复杂任务（长文/报告/方案/本体建模等）→ `cloud`（DeepSeek，需 key 就绪）
- 云端不可用（离线/无 key/HTTP 错）→ 自动降级 `local`
- `active=local` 时 → 一律走本地
- 手动指定：`solo run "任务" --tier remote|local`

## 环境变量

- `DEEPSEEK_API_KEY`：云端 DeepSeek API key，从环境读取，**不写入任何配置文件、不入仓库**。
- 旧格式 `provider.yaml` 的 `api_key_env` 同样支持（key 优先级：配置内 `api_key` 字段 > 环境变量 > 兜底读 `~/.env`）。

## 验证配置

```bash
solo setup              # 环境诊断（Python / Ollama / 配置 / 记忆库）
solo config             # 查看配置（脱敏，key 不显示）
# Web 前端：部署 → 开始部署；配置 → 测试连接
```

## 常见问题

- **本地模型慢/超时**：换更小的 ornith 模型，或确认 Ollama 在运行。
- **云端无 key**：报错提示 `未配置 API key` → 设 `DEEPSEEK_API_KEY` 环境变量（模型闭环铁律：明确报错，不静默降级）。
- **嵌入不可用**：记忆回退词重叠检索，不影响主功能。
- 完整部署步骤见 **`docs/部署手册.md`**。
