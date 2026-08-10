# solo-agent-kit — OpenClaw 设计/代码审查委托简报

> 委托人：zhengjinjun1975（技术负责人）
> 审查对象：solo-agent-kit v0.5.0 — 针对 FDE 的轻量化全栈工具，一人公司的必备能力
> 审查目的：设计审查 + 代码审查 + 完整测试 + 方法论目标缺口补齐 + 优化建议，供下一步工作

## 一、项目定位

**solo-agent-kit** 是一个**针对 FDE（工厂/前置部署工程师）的轻量化全栈 AI 工具**，一人公司的必备能力。
核心方法论：**本体优先 + 双套件（个人+工厂）+ 记忆/写作/代码/数据/建模 + 轻量（零依赖，核心 2121 行）**。
定位：不是通用 agent 框架，是"轻量化的 Hermes"——一个人干完整团队的活。

差异化锚点（竞品对比后确立）：
- **本体优先**：先建实体-关系本体再检索（ibl.ai 证实是 RAG 缺失层，轻量开源无人做）
- **方法论完整**：记忆+本体+skill+写作+代码+数据 一套闭环
- **双套件分离**：个人套件（solo/）+ 工厂套件（solo/factory/）
- **轻≠不行**：零依赖但能力完整，可审计

## 二、蓝图（VISION.md，40+ 章节方法论蓝图）

仓库根目录 `VISION.md`（569 行）——完整的方法论设计文档，包含：
- 定位/哲学/统一架构/模块设计/边界/推理模型/Obsidian处理
- 成长路线图（v0 CLI→v3 harness自进化）
- 开源合规/README骨架/成长不变量/工程落地清单
- 竞品定位（§25）+ 竞品反查优化（§26）
- 记忆演进理论（ACL2026）/harness工程（AHE论文）

## 三、架构

```
solo-agent-kit/
├── VISION.md          方法论蓝图(40+章)
├── README.md          功能化入口(本体优先锚定)
├── pyproject.toml     零依赖打包
├── LICENSE/NOTICE     Apache-2.0 + 派生声明
├── solo/              个人套件
│   ├── provider.py    模型分层(本地/远端/嵌入) + provider.yaml读取
│   ├── memory.py      三层两域记忆
│   ├── skill.py       可复用经验提取
│   ├── writing.py     六维写作检查
│   ├── code.py        代码库理解(impact/overview/explain)
│   ├── gen.py         代码/文档/审查生成
│   ├── task.py        任务状态控制面
│   ├── agent.py       AI原生对话路由(意图识别→调用套件)
│   ├── cli.py         命令入口(含factory命令/setup/config)
│   ├── web_server.py  极简Web后端(标准库REST API)
│   └── factory/       工厂套件
│       ├── clean.py   数据清洗(缺失/重复/异常值)
│       ├── stats.py   数据分析(描述/趋势/SPC/相关)
│       └── ontology.py 本体建模(设备/工单关系)
├── web/index.html     AI原生前端(OpenClaw式对话中心,浅色护眼)
├── examples/          5+2真实场景
└── tests/             18项pytest
```

## 四、审查要点（请逐项核查）

### 1. 设计审查
- 双套件分离（个人/工厂）是否合理？边界是否清晰？
- AI 原生对话路由（agent.py 意图识别）设计是否完备？意图覆盖是否够？
- provider.yaml 模型分层 + 降级兜底是否符合"轻≠不行"？
- 前端 AI 原生对话中心 + 浅色护眼配色是否符合工程化落地？

### 2. 代码审查
- solo/*.py + solo/factory/*.py + web_server.py 全部代码
- 已知遗留：CodeAgent 静态审查报 33 问题（13 major 圈复杂度 + 20 minor 误报）
  - major：clean/scan/index 等函数圈复杂度高（反过度工程可接受，是否该拆？）
  - minor：`from __future__ import annotations` 报未使用（误报，Python延迟注解）
  - 请复核哪些是真问题、哪些可接受、哪些必须改

### 3. 完整测试
- tests/test_core.py 18 项是否覆盖充分？
- 端到端 CLI 全流程（setup/run/skill/factory三件套/import/export/config）是否验证？
- Web API 全端点（/api/agent 8意图 + clean/stats/ontology/memory/skill/writing/gen/setup/config）是否验证？
- 前端渲染 + AI 路由 8/8 是否验证？

### 4. 方法论目标缺口补齐
对照 VISION 蓝图，检查：
- provider.yaml 真正生效（v0.4 已修）
- factory 进 CLI + Web API（v0.4/v0.5 已做）
- AI 原生对话路由（v0.5 已做）
- 前端工程化（v0.5 已做）
- 还有哪些蓝图承诺未落地？反过度工程哪些不该做？

## 五、待决策/建议项（供 OpenClaw 输出）

1. 圈复杂度高的函数（clean 24 / code.index 20）是否拆分？还是守反过度工程保留？
2. AI 原生路由用关键词启发式（v1）vs LLM 意图识别（v2）——现在该不该升级？
3. 前端是否需再加图表可视化（SPC 控制图/趋势图）？
4. 记忆层语义检索用 bigram 重叠（零依赖）vs sqlite-vec——是否该换？
5. harness 自进化（AHE 论文思想）是否该开始预留/实现？
6. 还有什么方法论点或能力缺口该补？

## 六、下一步工作建议

请输出：完整测试结果 + 代码审查报告（问题分级：必须改/建议改/可接受）+ 设计审查结论 + 方法论缺口清单 + 优化方案（按优先级）。供下一步迭代。

---
审查材料位置：`E:\open-source\solo-agent-kit\`
远程仓库：`github.com/zhengjinjun1975/solo-agent-kit`
