# solo-agent-kit

> ⭐ **觉得有用就给我们一个 Star** —— 你的 Star 让这个项目被更多人看见，支持我们持续迭代。
> [![GitHub stars](https://img.shields.io/github/stars/zhengjinjun1975/solo-agent-kit?style=social)](https://github.com/zhengjinjun1975/solo-agent-kit)

> **给 FDE（工厂/前置部署工程师）与一人公司的 AI 原生全栈工具；也是甲方/乙方工程师共用的开源算法底座。**
> 方法论决定一切：不是工具堆砌，是同一套方法论在不同层的落地。
> 零依赖，能打；单文件，能审；独立主体，不绑定平台；开源原子，可独立运行、可被上层组装。

<p align="center">
  <a href="https://github.com/zhengjinjun1975/solo-agent-kit/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License">
  </a>
  <a href="https://github.com/zhengjinjun1975/solo-agent-kit/blob/main/CHANGELOG.md">
    <img src="https://img.shields.io/badge/version-0.5.6-blue.svg" alt="Version">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.9%2B-blue.svg" alt="Python">
  </a>
  <a href="https://github.com/zhengjinjun1975/solo-agent-kit">
    <img src="https://img.shields.io/badge/deps-zero%20third--party-green.svg" alt="Zero third-party deps">
  </a>
</p>

## 目录

- [原子化定位（fde 域开源底座）](#原子化定位fde-域开源底座)
- [AI 原生思想](#ai-原生思想)
- [它解决什么](#它解决什么)
- [快速开始](#快速开始)
- [真实场景示例](#真实场景示例)
- [核心能力](#核心能力)
- [配置](#配置)
- [项目结构](#项目结构)
- [文档](#文档)
- [与 Obsidian 的关系](#与-obsidian-的关系)
- [开源与合规](#开源与合规)
- [限制与诚实声明](#限制与诚实声明)
- [贡献](#贡献)
- [来源与致谢](#来源与致谢)
- [License](#license)

## 原子化定位（fde 域开源底座）

solo 在生态「插件式原子智能体组装」架构中，作为 **fde 域开源原子底座**存在（架构定稿见 `_os/plugin-agent-architecture.md`）：

- **fde 域四原子**：`fde`（现场流程 D0-D4 工具箱）、`memory`（三层两域记忆）、`monitor`（设备监测）、`write`（中文写作）——每个都是可独立运行、可被上层组装的开源原子；内部另有 `codereview`（代码审查）原子。
- **甲方乙方工程师共用**：乙方工程师用同一套开源底座做交付辅助（起草/记忆/方法论），甲方工程师用它自持自运行（本体/监测/决策）——共用同一算法内核，不区分阵营。
- **开源算法 + 闭源编排边界**：算法/流程内核全部开源（Apache-2.0，可免费使用、可被闭源编排层调用）；唯一不进开源的是编排/组装/交付增值。闭源侧只经公开能力接口调用本仓库原子，删掉闭源编排器后，本仓库全开源子图仍自洽可独立运行。
- **FDE 先开源**：solo 算法与流程内核优先开源，甲方可自持；对外交付增值由闭源 `deliver` 原子承接，不把 FDE 本身闭源化。详见 [开源与合规](#开源与合规)。

## AI 原生思想

solo-agent-kit 不是又一个工具合集。它是一个由方法论决定一切的 AI 原生系统，每个能力模块都不是为了"有这个功能"而存在，而是一套验证过的方法论在某个具体层的落地。

它回答的不是"你能做什么"，而是"你用什么原则思考"。

五个方法论点，贯穿所有模块：

| 方法论 | 它意味着什么 | 落地的能力 |
|---|---|---|
| **单一事实源** | 同一件事只有一个权威位置，写入路径唯一 | 记忆、项目上下文、决策树 |
| **本体优先** | 先建实体-关系-属性语义结构，再谈检索与理解 | 本体建模、知识检索 |
| **反过度工程** | 一人公司不需要团队治理；单文件能解决就不拆框架 | 全套件零第三方依赖 |
| **诚实定位** | 方法论加思路，非对标大厂；能力边界写清楚 | 每模块可独立 import、可审计 |
| **原子化组装** | 算法进开源、编排进闭源；一个能力一个原子，可独立运行可被组装 | fde 域四原子（fde/memory/monitor/write） |

### 为什么是"本体优先"

RAG 检索文本，本体检索知识。solo 先建实体-关系的语义结构，再谈检索，这让 agent 理解你的领域里什么是真的、什么能行动。这不只是更准的搜索，是整个系统的地基。社区普遍印证这是 RAG 的缺失层，只是轻量开源无人做。

## 它解决什么

| 痛点 | 现状 | solo 的解法 |
|---|---|---|
| 记忆断层 | 每次会话重新介绍背景 | 三层两域记忆，词重叠检索，可选 embed 向量 |
| 方法论不沉淀 | 踩过的坑散在聊天记录 | skill 从任务提取可复用经验 |
| 绑定平台 | 被某 agent 框架锁死 | 独立主体，零依赖，拉下来即用 |
| 领域检索不准 | RAG 返回相似文本而非知识 | 本体优先，检索知识 |
| 算法与编排边界不清 | 开源库把交付/编排一起开源，商业化被动、甲方难自持 | 算法进开源、编排进闭源，边界铁律；甲方拿开源即可自持自运行 |

## 快速开始

FDE/一人公司交付工具链覆盖：**入场基线（D0）→ 建模审查（D1）→ 验证补全（D2）→ 培训试运行（D3）→ 交付（D4）→ 验收闭环（survey）→ 设备监测（monitor）**，同一套命令同时服务乙方交付辅助与甲方自持自运行。

```bash
# 安装
pip install solo-agent-kit        # 或 git clone 后 pip install .
solo init                          # 初始化记忆库
solo run "写一篇公众号推文"        # 走完整方法论
```

FDE（工厂/前置交付）工具箱：
```bash
solo industry-list                # 列出已登记行业（行业→kb/词典联动注册表）
solo industry-set 阀门制造 <data.csv>   # 改行业→自动重建 问题集/词典/工厂契约/审查队列/报告
solo industry-current             # 查看当前行业及生效配置
solo draft-questions <data.csv>          # 起草 benchmark 问题集（FDE D0）
solo lexicon-draft <data.csv>            # 起草词典初稿（FDE D1）
solo to-factory-lexicon <data.csv>       # 词典→工厂本体 lexicon 契约
solo to-review-items <data.csv>          # 词典→闭源 review 待确认队列
solo report-draft --hit 0.8 --questions 20 --hits 15   # 起草交付报告（FDE D4）
solo survey-outline                # 需求访谈提纲（行业数据驱动）
solo survey-structure <name> "<痛点>"   # 结构化一条需求（编号 R-xxx）
solo survey-srs <name> / survey-acceptance <name>   # 生成 SRS / 验收清单
```

个人套件 CLI：
```bash
solo code-review <file>.py         # 代码审查（静态分析+0-100评分）
solo writing-ai-taste "文本" --style report      # 中文 AI 味自检（评分+建议+自洽结论）
solo writing-write-natural "文本" --style tweet   # 风格改写 + AI 味复检闭环
solo memory-note "事实" --tag 经验  / memory-search "查询"   # 温域记忆 记/查
solo optmem-note "经验" / optmem-search "查询"             # OptMem 全局记忆 记/查
solo onto-to-nt <data.csv>         # CSV→本体→N-Triples
solo onto-answer <data.csv> "有多少台设备"   # 本体聚合问答（计数/极值/枚举）
solo onto-search <data.csv> "设备"          # 本体三元组检索
```

工厂数据三件套：
```bash
solo factory-clean <data.csv>      # 数据清洗（缺失/重复/异常值）
solo factory-stats <data.csv>      # 数据分析（描述/趋势/SPC，自动跳过 id 主键列）
solo factory-onto <data.csv>       # 工厂本体建模
```

### 设备监测 P0（借鉴 DataBuff「指标→存储→告警→AI问数」骨架，零依赖）

```bash
solo monitor-demo --rounds 12 --temp-high 80.0   # 端到端演示：设备数据→告警→工单→AI问数
solo monitor-ask "哪台设备温度过高"              # AI问数（自然语言查设备/告警/工单）
solo monitor-ingest d1 temperature 95.0          # 接入一条设备指标（自动评估告警→建工单）
```

- 统一指标存储（`device_metric` 时序 + 分钟预聚合）、告警引擎（阈值 + 突变检测 + 恢复自动关闭）、工单状态机（open→in_progress→done）、MQTT 接入抽象、AI 问数。
- 详见 `docs/databuff-P0-设备监测清单.md`。

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

> **原子化对应**：以下模块即 fde 域开源原子的核心实现——`memory`→`solo-memory`、`factory/monitor`→`solo-monitor`、`writing`→`zh-write`、`agent/cli/factory/*`→`solo-fde`、`code_review`→`code-review`。改壳不改核心，模块可直接被上层原子化组装复用（见 [原子化定位](#原子化定位fde-域开源底座)）。

**个人套件**（`solo/`，一人公司日常）：

| 模块 | 能力 | 方法论锚点 |
|---|---|---|
| `memory.py` | 三层两域记忆 + OptMem 互通 | 单一事实源加热域/温域/冷域 |
| `skill.py` | 可复用经验 | 从任务提取，带版本与触发边界 |
| `writing.py` | 六维写作检查 + 风格改写 | D1错字/D2标点/D3语病/D4数字/D5去AI味/D6活人感 |
| `code_review.py` | 代码审查 | 静态分析 + 0-100 评分（对齐 codeagent 口径） |
| `code.py` | 代码库理解 | impact 影响分析，overview/explain |
| `task.py` | 任务/工单状态 | 断点续跑、决策门、可证伪预期 |

**FDE/工厂套件**（`solo/factory/`，FDE 交付工具箱）：

| 模块 | 能力 | 方法论锚点 |
|---|---|---|
| `data.py` | 数据清洗/分析 | 缺失/重复/异常值，SPC/趋势 |
| `ontology.py` | 本体建模/问答 | 计数/极值/枚举聚合问答，N-Triples 导出 |
| `decisions.py` | 决策规则引擎 | 阈值表 + 行业阈值覆盖 |
| `survey.py` | 需求→验收生命周期 | 访谈提纲/结构化/SRS/验收清单/勾稽 |
| `assist.py` | FDE 交付辅助 | 问题集/词典/工厂契约/审查队列/报告起草 |
| `industry.py` | 行业→kb 联动 | 改行业自动重建全部 FDE 产物 |
| `quote.py`/`train.py`/`support.py` | 报价/培训/工单运维 | FDE 全域交付能力 |
| `monitor.py` | 设备数据监测 P0 | 指标存储/告警引擎/工单状态机/MQTT接入/AI问数（借鉴 DataBuff 骨架） |

**插件**（`solo/plugins/`，可降级）：

| 模块 | 能力 | 依赖 |
|---|---|---|
| `obsidian.py` | Obsidian 知识库集成：报告归档/检索/经验沉淀 | 零依赖 |
| `visualize.py` | 数据可视化：SPC 控制图/趋势图/异常标记 | matplotlib(可选) |
| `excel_report.py` | Excel 报告导出 | openpyxl(可选) |
| `netscan.py` | 网络扫描/资产发现 | 零依赖 |

### 插件设计说明

插件不是功能堆砌，而是**在零依赖内核之上的可降级能力层**。三个设计原则：

**一、内核零依赖，插件可降级**
核心套件（记忆/写作/代码/数据/建模）只用标准库，任何机器拉下来即用。插件承载"增强但不必需"的能力，依赖本机已装工具（matplotlib/文件系统），缺失时明确降级不崩溃：

```bash
solo plugins list          # 查看各插件可用性（obsidian/visualize 等）
```

**二、可靠优先，用本机已有的**
插件优先复用本机已装工具，不引入脆弱依赖。Obsidian 集成直接用文件系统读写 vault（`~/obsidian-vault`），因为 Obsidian 笔记应用无官方 CLI；可视化复用 matplotlib（本机已装），零新增依赖。

**三、能力可扩展，注册表驱动**
`plugins/__init__.py` 的注册表声明每个插件的依赖与能力。新增插件只需注册模块，`list_plugins()` 自动显示可用性。这是 FDE 套件"进厂区后按需加载能力"的机制：用不到的不装，装上的必须可靠。

## 配置

模型配置仿工厂本体开源风格，位于 **`config/model_config.json`**（仓库内已带默认值，一般无需改动即可用）。

```jsonc
{
  "active": "cloud",        // 默认路由：cloud（复杂任务走云端）/ local（全程本地）
  "routing": {              // 智能路由：simple→local，complex→cloud，离线降级 local
    "policy": "simple->local ; complex->cloud ; offline->fallback local ; all-down->rule/retrieval",
    "complex_models": ["cloud", "local"],
    "simple_models": ["local"],
    "offline_fallback": true
  },
  "embedding": { "type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "nomic-embed-text" },
  "models": {
    "local":  { "type": "ollama", "base_url": "http://127.0.0.1:11434", "model": "ornith:latest" },
    "cloud":  { "type": "openai", "base_url": "https://api.deepseek.com", "model": "deepseek-chat", "api_key": "" }
  }
}
```

- **本地 ornith**（Ollama，无需 key）跑轻量推理；**云端 DeepSeek**（`api_key` 留空则读 `DEEPSEEK_API_KEY` 环境变量）跑复杂推理。
- 旧版 `provider.yaml`（`provider.local/remote/embed`）**仍兼容**，读取顺序：`config/model_config.json` → `provider.yaml` → `~/.solo/provider.yaml`。
- 完整部署说明见 **`docs/部署手册.md`**。

## 项目结构

```
solo-agent-kit/
├── solo/                 # 个人套件（零依赖，fde 域原子核心实现）
│   ├── app.py            #   统一服务门面（业务单一事实源）
│   ├── cli.py            #   CLI 命令入口（agent-first，JSON out）
│   ├── memory.py         #   三层两域记忆 + OptMem 互通  → solo-memory 原子
│   ├── writing.py        #   六维写作检查 + 风格改写      → zh-write 原子
│   ├── code_review.py    #   代码审查（静态分析+0-100评分）→ code-review 原子
│   ├── code.py           #   代码库理解
│   ├── task.py           #   任务/工单状态
│   └── factory/          # FDE 交付工具箱 → solo-fde 原子
│       ├── data.py       #   数据清洗/分析(SPC)
│       ├── ontology.py   #   本体建模/聚合问答
│       ├── decisions.py  #   决策规则引擎
│       ├── survey.py     #   需求→验收生命周期
│       ├── assist.py     #   FDE 交付辅助（问题集/词典/契约/审查队列/报告）
│       ├── industry.py   #   行业→kb 联动（改行业自动重建）
│       ├── monitor.py    #   设备数据监测 P0 → solo-monitor 原子
│       └── quote.py/train.py/support.py   # 报价/培训/工单运维
├── solo/plugins/         # 可降级插件（obsidian/visualize/excel_report/netscan）
├── config/               # model_config / industries / decisions 配置
├── examples/             # 真实场景示例
├── docs/                 # 设计文档（含架构/原子化定位）
├── web/                  # Web 前端
└── CHANGELOG.md
```

## 文档

- [VISION.md](VISION.md) — 设计哲学与核心思想
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 分层架构 + 原子化定位（fde 域原子/开源闭源边界）
- [docs/FDE套件运行手册.md](docs/FDE套件运行手册.md) — FDE 交付辅助运行手册（能力边界）
- [docs/部署手册.md](docs/部署手册.md) — 部署与配置
- [docs/](docs/) — 其余设计文档（厂区运维、插件体系）
- [CHANGELOG.md](CHANGELOG.md) — 版本记录

## 与 Obsidian 的关系

solo 的记忆自包含，独立运行零依赖。已用 Obsidian 的可选互通：

```bash
solo import-obsidian  <vault路径>   # 导入已有笔记为记忆
solo export-markdown               # 导出记忆为 Markdown，可回写
```

## OptMem 互通（可选增强）：FDE 经验/方法论 note 进全局记忆

`Memory.optmem_note()/optmem_search()`（模块级 `solo.memory.optmem_note/optmem_search`）把
**FDE 工具箱经验/方法论**固化进 OptMem（可选增强，跨项目、跨会话复用）。**不侵入主流程、零依赖**（纯标准库），失败静默。

```python
from solo.memory import Memory, optmem_note
Memory().optmem_note("交付方法论: 验收前先自测 e2e 再交付, 少返工")   # 沉淀
Memory().optmem_search("FDE 交付方法论 返工")                       # 语义检索
```

```bash
python -m solo.memory        # 自检: 沉淀一条示例方法论并检索回看
```

可用 `OPTMEM_NOTE=0` 关闭。solo 自带的三层两域记忆（`~/.solo/memory`）仍是主存；OptMem 作为
跨工具全局事实层的可选同步目标。

## 开源与合规

solo 遵循生态「算法进开源、编排进闭源」的 Open-Core 边界（详见 `_os/oss-close-boundary-license.md`），合规口径如下：

- **开源算法免费**：solo 全部算法/流程内核以 **Apache-2.0** 开源，免费使用、可自由修改与分发；甲方可拿到源码自持自运行，零授权费、零第三方依赖。
- **可被闭源编排调用**：本仓库开源原子可作为能力底座，被闭源编排/组装层（assembler/orchestrator）经**公开能力接口**调用。被调用是合法的 Apache-2.0 用途；但闭源侧**不得**反向依赖、**不得** import 本仓库内部私有实现，开源原子本身也**不会反向依赖任何闭源组件**——删掉编排器，全开源子图仍自洽可独立运行。
- **FDE 先开源**：solo（FDE 域）的算法与流程内核优先开源、甲方可自持；其「对外服务/交付」等增值如需闭源，由闭源的 `deliver` 原子承接，不把 FDE 本身闭源化，也不要求甲方为使用核心算法付费。
- **借鉴声明**：设备监测 P0 借鉴 DataBuff 的「指标→存储→告警→AI问数」**设计思想**，未复制代码（DataBuff 为 AGPL，仅留思路不留代码，规避传染）。详见 [NOTICE](NOTICE)。
- **零依赖合规**：核心仅用 Python 标准库，无第三方依赖，无 AGPL/传染性依赖进入开源层。

## 限制与诚实声明

solo 不是通用 agent 框架，不试图替代 Claude Code、Cursor 等成熟工具。

- 不是又一个通用 Agent 框架。它轻量、方法论驱动、非对标大厂。
- 不是 AI 替代人类的计划。人留在循环里，agent 是帮手不是取代。
- 不是已完成的产品。诚实标注什么能用、什么在长。
- 定位：一人公司与 FDE 的方法论套件，同时是甲方/乙方工程师共用的开源算法底座。本体优先，能力边界清楚；算法开源、编排闭源、FDE 先开源（见 [开源与合规](#开源与合规)）。
- **本地信任边界**：Web 后端默认只绑定 `127.0.0.1`，属本地单机工具。远程运维（SSH）、文件浏览、数据读取等能力设计为本机使用，**不要**将服务绑定到公网地址对外暴露（否则远程 SSH 执行 / 文件浏览将对外可用）。绑定非本机地址前请自行评估信任边界。
- **远程运维（`/api/remote`）需配置 SSH 目标**：远程执行依赖本机 `ssh` 命令 + 已配置的 SSH key（`~/.ssh`），连接信息取自身份 `~/.solo/site.json` 台账或请求体 `host/user/port`。SSH 目标未配置（缺 `ssh` 命令/未配 key）时接口会返回明确的 `ok:false` 提示，而不会伪装成成功——请先配置台账再调用。
- **SPC 控制图需 matplotlib（可选）**：核心套件零依赖；SPC 控制图等可视化由 `solo/plugins/visualize.py` 承载，依赖本机 `matplotlib`（可选）。未安装时 `/api/charts/spc` 返回 `ok:false` + 数值统计提示，不崩溃、不 500，可改用 `/api/stats` 获取数值统计。

## 贡献

欢迎提交 issue 与 PR。核心原则：

- 保持零第三方依赖（只用标准库）
- 每个模块单文件、可独立 import、可审计
- 非平凡逻辑留一个可运行的测试
- 方法论驱动优先于功能堆砌
- 遵守原子化边界：开源原子不得依赖任何闭源组件；为封装而改核心的需求先进 TODO，不进原子化壳层

## 来源与致谢

solo-agent-kit 借鉴了多个项目的方法论，非代码复制。详见 [NOTICE](NOTICE)。

## License

[Apache-2.0](LICENSE)。
