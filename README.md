# solo-agent-kit

> 一人公司/中早期创业者的**本体优先**方法论 Agent —— 记忆/写作/代码/开源，一个人干完整活。
> **轻量，但能打。零依赖，但方法论完整。** 不是通用 agent，是专为人公司定制的方法论套件。

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](CHANGELOG.md)

## 为什么是"本体优先"（不是又一个记忆库/RAG）

- RAG 检索文本，本体检索知识——solo 先建实体-关系语义结构，再检索
- 这不只是更准的搜索，是让 agent 理解"你的领域里什么是真的、什么能行动"
- 这是 solo 区别于全部同类竞品的核心（ibl.ai 证实这是 RAG 的缺失层，但轻量开源无人做）

## 它解决什么

| 痛点 | 现状 | solo 的解法 |
|---|---|---|
| 记忆断层 | 每次会话重新介绍背景 | 三层两域记忆，语义检索 |
| 方法论不沉淀 | 踩过的坑散在聊天记录 | skill 从任务提取可复用经验 |
| 绑定平台 | 被某 agent 框架锁死 | 独立主体，零依赖，拉下来即用 |
| 领域检索不准 | RAG 返回相似文本非知识 | 本体优先，检索知识 |

## 快速开始

```bash
pip install solo-agent-kit   # 或 git clone 后 pip install .
solo init                     # 初始化记忆库
solo run "写一篇公众号推文"    # 走完整方法论
```

## 真实场景示例（证明"轻≠不行"）

`examples/` 演示一人公司的 3 个真实场景（零依赖跑通）：

```bash
# 场景①：写公众号推文（记忆装载→生成→六维检查→提交）
python examples/example_01_wechat_post.py "本体驱动的知识管理"

# 场景②：查知识（本体优先检索：实体关系而非相似文本）
python examples/example_02_knowledge_query.py "阀门厂"

# 场景③：开源发布前检查（脱敏扫描+代码影响分析+版本核查）
python examples/example_03_oss_preflight.py <项目目录>
```

## 核心能力

| 模块 | 能力 | 说明 |
|---|---|---|
| `ontology.py` | 本体建模 | CSV→实体-关系-属性，语义锚点 |
| `memory.py` | 三层两域记忆 | 热域画像/温域事实+场景/冷域归档，语义检索 |
| `skill.py` | 可复用经验 | 从任务提取，带版本/触发边界 |
| `writing.py` | 六维写作检查 | 错字/标点/语病/数字/去AI味/活人感 |
| `code.py` | 代码影响分析 | 改代码前 impact() |
| `task.py` | 任务状态 | 断点续跑 |

## 配置（本地/远端模型分层）

复制 `provider.yaml.example` 为 `provider.yaml`：

```yaml
provider:
  local:   # 轻量推理（记忆/写作/压缩）
    type: ollama
    model: ornith:latest
  remote:  # 复杂推理（本体建模/复杂代码）
    type: openai-compatible
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
  embed:   # 语义嵌入（记忆检索，本地）
    type: ollama
    model: nomic-embed-text:latest
```

## 与 Obsidian 的关系

solo 的记忆是自包含的（独立运行零依赖）。已用 Obsidian 的可选互通：
```bash
solo import-obsidian  <vault路径>   # 导入已有笔记为记忆
solo export-markdown               # 导出记忆为 Markdown 可回写
```

## 限制与诚实声明

solo 不是通用 agent 框架，不试图替代 Hermes、Claude Code 等成熟工具。
- 不是又一个通用 Agent 框架——它轻量、方法论驱动、非对标大厂
- 不是 AI 替代人类的计划——人留在循环里，agent 是帮手不是取代
- 不是已完成的产品——诚实标注什么能用、什么在长
- 定位：一人公司/中早期创业者的方法论套件，本体优先，能力边界清楚

## 来源与致谢

solo-agent-kit 借鉴了多个项目的方法论（非代码复制）。详见 [NOTICE](NOTICE)。

## 路线图

```
v0.1  骨架 + 记忆/模型最小闭环（当前）
v0.2  方法论铺满：本体/写作/代码/skill/task 全接入
v1.0  首个开源发布：方法论完整、文档齐全
v2.0  gateway 常驻 + 消息平台接入
v3.0  harness 自进化 + MCP 生态
```

## License

Apache-2.0 — 见 [LICENSE](LICENSE)。
