# solo-agent-kit

> **给 FDE（工厂/前置部署工程师）与一人公司的 AI 原生全栈工具。**
> 方法论决定一切：不是工具堆砌，是同一套方法论在不同层的落地。
> 零依赖，能打；单文件，能审；独立主体，不绑定平台。

<p align="center">
  <a href="https://github.com/zhengjinjun1975/solo-agent-kit/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License">
  </a>
  <a href="https://github.com/zhengjinjun1975/solo-agent-kit/blob/main/CHANGELOG.md">
    <img src="https://img.shields.io/badge/version-0.8.4-blue.svg" alt="Version">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.9%2B-blue.svg" alt="Python">
  </a>
  <a href="https://github.com/zhengjinjun1975/solo-agent-kit">
    <img src="https://img.shields.io/badge/deps-zero%20third--party-green.svg" alt="Zero third-party deps">
  </a>
</p>

## 目录

- [AI 原生思想](#ai-原生思想)
- [它解决什么](#它解决什么)
- [快速开始](#快速开始)
- [真实场景示例](#真实场景示例)
- [核心能力](#核心能力)
- [配置](#配置)
- [项目结构](#项目结构)
- [文档](#文档)
- [与 Obsidian 的关系](#与-obsidian-的关系)
- [限制与诚实声明](#限制与诚实声明)
- [贡献](#贡献)
- [来源与致谢](#来源与致谢)
- [License](#license)

## AI 原生思想

solo-agent-kit 不是又一个工具合集。它是一个由方法论决定一切的 AI 原生系统，每个能力模块都不是为了"有这个功能"而存在，而是一套验证过的方法论在某个具体层的落地。

它回答的不是"你能做什么"，而是"你用什么原则思考"。

四个方法论点，贯穿所有模块：

| 方法论 | 它意味着什么 | 落地的能力 |
|---|---|---|
| **单一事实源** | 同一件事只有一个权威位置，写入路径唯一 | 记忆、项目上下文、决策树 |
| **本体优先** | 先建实体-关系-属性语义结构，再谈检索与理解 | 本体建模、知识检索 |
| **反过度工程** | 一人公司不需要团队治理；单文件能解决就不拆框架 | 全套件零第三方依赖 |
| **诚实定位** | 方法论加思路，非对标大厂；能力边界写清楚 | 每模块可独立 import、可审计 |

### 为什么是"本体优先"

RAG 检索文本，本体检索知识。solo 先建实体-关系的语义结构，再谈检索，这让 agent 理解你的领域里什么是真的、什么能行动。这不只是更准的搜索，是整个系统的地基。社区普遍印证这是 RAG 的缺失层，只是轻量开源无人做。

## 它解决什么

| 痛点 | 现状 | solo 的解法 |
|---|---|---|
| 记忆断层 | 每次会话重新介绍背景 | 三层两域记忆，词重叠检索，可选 embed 向量 |
| 方法论不沉淀 | 踩过的坑散在聊天记录 | skill 从任务提取可复用经验 |
| 绑定平台 | 被某 agent 框架锁死 | 独立主体，零依赖，拉下来即用 |
| 领域检索不准 | RAG 返回相似文本而非知识 | 本体优先，检索知识 |

## 快速开始

```bash
# 安装
pip install solo-agent-kit        # 或 git clone 后 pip install .
solo init                          # 初始化记忆库
solo run "写一篇公众号推文"        # 走完整方法论
```

厂区运维（FDE 进厂区）：
```bash
solo site use 华东一厂              # 进入厂区运维模式，定位
solo site devices                  # 查看该厂区设备台账
solo site add-device MES服务器 192.168.1.10 --user root   # 登记设备
solo site role on-site             # 部署角色：laptop本机 / on-site部署在对方机
```

## 真实场景示例

`examples/` 演示一人公司加 FDE 的真实场景，零依赖跑通：

```bash
# 场景① 写公众号推文：记忆装载→生成→六维检查→脱敏→提交
python examples/example_01_wechat_post.py "本体驱动的知识管理"

# 场景② 查知识：本体优先检索，实体关系而非相似文本
python examples/example_02_knowledge_query.py "阀门厂"

# 场景③ 开源发布前检查：脱敏扫描+代码影响分析+版本核查
python examples/example_03_oss_preflight.py <项目目录>

# 场景④ 工厂级本体建模：设备台账+关系声明→实体关系本体→结构化查询
python examples/example_04_factory_ontology.py
```

## 核心能力

**个人套件**（`solo/`，一人公司日常）：

| 模块 | 能力 | 方法论锚点 |
|---|---|---|
| `memory.py` | 三层两域记忆 | 单一事实源加热域/温域/冷域 |
| `skill.py` | 可复用经验 | 从任务提取，带版本与触发边界 |
| `writing.py` | 六维写作检查 | D1错字/D2标点/D3语病/D4数字/D5去AI味/D6活人感 |
| `desensitize.py` | 写作脱敏 | 掩码 IP/手机/邮箱/金额/自定义词，防泄露给 LLM |
| `gen.py`、`code_agent.py` | 代码生成/审查/测试 | 静态分析加双层审查加生成测试 |
| `code.py` | 代码库理解 | impact 影响分析，overview/explain |
| `task.py` | 任务状态 | 断点续跑、决策门、可证伪预期 |

**厂区套件**（`solo/factory/`，FDE 进厂区）：

| 模块 | 能力 | 方法论锚点 |
|---|---|---|
| `site.py` | 厂区配置与定位 | 设备台账，部署角色 laptop/on-site |
| `remote.py` | 远程运维 | SSH 设备名重载，采集/执行/日志 |
| `monitor.py` | 设备监控 | monitor_device，批量巡检 |
| `data_connector.py` | 数据源统一 | connect(type=device) 远程拉厂区数据 |
| `clean.py`、`stats.py`、`ontology.py` | 数据三件套 | 清洗、SPC 分析、本体建模，对接厂区数据 |

**插件**（`solo/plugins/`，可降级）：

| 模块 | 能力 | 依赖 |
|---|---|---|
| `obsidian.py` | Obsidian 知识库集成：报告归档/检索/经验沉淀 | 零依赖 |
| `visualize.py` | 数据可视化：SPC 控制图/趋势图/异常标记 | matplotlib(可选) |

### 插件设计说明

插件不是功能堆砌，而是**在零依赖内核之上的可降级能力层**。三个设计原则：

**一、内核零依赖，插件可降级**
核心套件（记忆/写作/代码/数据/建模）只用标准库，任何机器拉下来即用。插件承载"增强但不必需"的能力，依赖本机已装工具（matplotlib/文件系统），缺失时明确降级不崩溃：

```bash
solo plugins list          # 查看各插件可用性（obsidian/visualize 等）
```

**二、可靠优先，用本机已有的**
插件优先复用本机已装工具，不引入脆弱依赖。Obsidian 集成直接用文件系统读写 vault（`D:/knowledge-base/obsidian-vault/`），因为 Obsidian 笔记应用无官方 CLI；可视化复用 matplotlib（本机已装），零新增依赖。

**三、能力可扩展，注册表驱动**
`plugins/__init__.py` 的注册表声明每个插件的依赖与能力。新增插件只需注册模块，`list_plugins()` 自动显示可用性。这是 FDE 套件"进厂区后按需加载能力"的机制：用不到的不装，装上的必须可靠。

## 配置

本地与远端模型分层。复制 `provider.yaml.example` 为 `provider.yaml`：

```yaml
provider:
  local:   # 轻量推理：记忆/写作/审查
    type: ollama
    model: ornith:latest
  remote:  # 复杂推理：代码生成/复杂分析
    type: openai-compatible
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
  embed:   # 语义嵌入：记忆检索，本地
    type: ollama
    model: nomic-embed-text:latest
```

## 项目结构

```
solo-agent-kit/
├── solo/                 # 个人套件（零依赖）
│   ├── memory.py         #   三层两域记忆
│   ├── writing.py        #   六维写作检查
│   ├── desensitize.py    #   写作脱敏
│   ├── code_agent.py     #   代码生成/审查/测试
│   ├── site.py           #   厂区配置与定位
│   └── factory/          # 厂区套件
│       ├── clean.py      #   数据清洗
│       ├── stats.py      #   数据分析(SPC)
│       ├── ontology.py   #   本体建模
│       ├── remote.py     #   远程运维
│       └── monitor.py    #   设备监控
├── examples/             # 真实场景示例
├── docs/                 # 设计文档
├── web/                  # Web 前端
└── CHANGELOG.md
```

## 文档

- [VISION.md](VISION.md) — 设计哲学与核心思想
- [docs/](docs/) — 设计文档（厂区运维、插件体系）
- [CHANGELOG.md](CHANGELOG.md) — 版本记录

## 与 Obsidian 的关系

solo 的记忆自包含，独立运行零依赖。已用 Obsidian 的可选互通：

```bash
solo import-obsidian  <vault路径>   # 导入已有笔记为记忆
solo export-markdown               # 导出记忆为 Markdown，可回写
```

## 限制与诚实声明

solo 不是通用 agent 框架，不试图替代 Hermes、Claude Code 等成熟工具。

- 不是又一个通用 Agent 框架。它轻量、方法论驱动、非对标大厂。
- 不是 AI 替代人类的计划。人留在循环里，agent 是帮手不是取代。
- 不是已完成的产品。诚实标注什么能用、什么在长。
- 定位：一人公司与 FDE 的方法论套件。本体优先，能力边界清楚。

## 贡献

欢迎提交 issue 与 PR。核心原则：

- 保持零第三方依赖（只用标准库）
- 每个模块单文件、可独立 import、可审计
- 非平凡逻辑留一个可运行的测试
- 方法论驱动优先于功能堆砌

## 来源与致谢

solo-agent-kit 借鉴了多个项目的方法论，非代码复制。详见 [NOTICE](NOTICE)。

## License

[Apache-2.0](LICENSE)。
