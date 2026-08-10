# SoloAgentKit 配置文档

> 模型分层配置：本地（Ollama）+ 远端（OpenAI 兼容）+ 嵌入。零依赖。

## 配置文件位置

`~/.solo/provider.yaml`（复制 `provider.yaml.example` 创建）

## 配置字段

```yaml
provider:
  # 轻量推理 → 本地 Ollama（快/免费/私有）
  local:
    type: ollama
    base_url: http://127.0.0.1:11434
    model: ornith:latest

  # 复杂推理 → 远端（强），key 从环境变量读，不落盘
  remote:
    type: openai-compatible
    base_url: https://api.deepseek.com
    model: deepseek-chat
    api_key_env: DEEPSEEK_API_KEY   # 环境变量名（值在环境，不在文件）

  # 嵌入 → 本地（记忆向量检索用，可选）
  embed:
    type: ollama
    base_url: http://127.0.0.1:11434
    model: nomic-embed-text
```

## 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| `provider.local` | 推荐 | 本地 Ollama 配置 |
| `provider.local.base_url` | 否 | 默认 `http://127.0.0.1:11434` |
| `provider.local.model` | 是 | 本地模型名（如 ornith:latest）|
| `provider.remote` | 可选 | 远端模型（复杂任务）|
| `provider.remote.base_url` | 是 | API 端点 |
| `provider.remote.model` | 是 | 远端模型名 |
| `provider.remote.api_key_env` | 是 | API key 的环境变量名（不存值）|
| `provider.embed` | 可选 | 嵌入模型（记忆向量检索）|

## 模型分层逻辑（agent 对话）

- 简单对话/短任务 → `local`（本地，快）
- 复杂任务（写长文/报告/方案）→ `remote`（需 key 就绪）
- 嵌入 → 本地 embed（记忆检索）

## 环境变量

- `DEEPSEEK_API_KEY`（或你在 api_key_env 配置的其他名）：远端 API key，从环境读取，**不写入任何文件**

## 验证配置

```bash
solo setup              # 环境诊断
solo config             # 查看配置（脱敏）
# Web 前端：部署 → 开始部署；配置 → 测试连接
```

## 常见问题

- **本地模型慢/超时**：换更小的 ornith 模型，或确认 Ollama 在运行
- **远端无 key**：报错提示 `环境变量 XXX 未设置` → 设置对应环境变量
- **嵌入不可用**：记忆回退词重叠检索，不影响主功能
