# Changelog

所有显著变更记录在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.4.0] - 2026-08-10

### 新增
- **provider.yaml 真正生效**：`Provider.from_file()` + `load_config()` 零依赖 YAML 解析，模型分层（本地/远端/嵌入）从配置文件读取
- **factory 模块进 CLI**：`solo factory-clean` / `factory-stats` / `factory-onto` 命令
- **部署检查**：`solo setup`（Python/Ollama/config/记忆库 四检）
- **配置查看**：`solo config`（provider.yaml 脱敏显示）
- **可视化前端**：`web/index.html`（单文件零依赖）——融合 OpenClaw（暗色玻璃拟态）+ WorkBuddy（办公多面板），工业蓝（工厂套件）+ 暖橙（个人套件），涵盖全部套件能力
- 定位升级：**针对 FDE 的轻量化全栈工具，一人公司的必备能力**

### 修复
- provider.py 结构错乱：load_config 插入致 Provider.complete 游离（死代码），重写恢复类结构

## [0.3.0] - 2026-08-10

### 新增
- **工厂现场数据套件**：`solo/factory/`（clean + stats + ontology 三件套）
  - `clean.py`：数据清洗（缺失/重复/异常值 IQR-zscore/类型推断）
  - `stats.py`：数据分析（描述统计/趋势/异常检测/SPC控制图/相关性）
  - `ontology.py`：工厂本体建模（从 solo/ 根移入）
- **个人套件 vs 工厂套件分离**：`solo/` 根保留个人能力（memory/skill/writing/gen/code/task/agent），工厂能力独立 `solo/factory/` 子包，可独立导入
- `examples/example_06_factory_data.py`：工厂数据清洗→分析→异常检测闭环
- 测试扩至 18 项（工厂数据清洗/分析）

### 修复
- stats 异常检测：IQR 法对单离群点比 zscore 稳健（zscore 会被离群点拉高 std）

### 方法论
- 套件分类：个人套件（一人公司日常）与工厂套件（工厂现场 FDE）解耦，各司其职

## [0.2.0] - 2026-08-10

### 新增
- **工厂级本体建模**（差异化核心落点）：ontology.py 升级关系建模
  - 对象属性声明（外键列→target_class，对齐 factory-ontology relations.json）
  - 多实体加载 + build 补全参照类
  - query/neighbors 实体间导航 + answer 工厂问题解答（零 LLM 结构化）
- **多表工厂本体**：设备台账 + 工单 → 跨实体关联查询（工单→设备→设备类型）
- FDE 能力：`gen.py`（代码生成/工程文档/代码审查）+ `code.overview/explain`（代码库理解）
- `examples/example_04_factory_ontology.py`（工厂单表）+ `example_05_factory_multi_ontology.py`（多表）
- 测试扩至 16 项（工厂关系/多表关联/code库理解/gen签名）

### 修复
- ontology 关系索引未存 rel 字段导致查询空，现已存
- 清理 3 处未使用 import（agent 的 ontology_mod、memory/skill 的 re）——CodeAgent 静态审查发现

### 方法论
- 定位升级：OPC 与工厂级 FDE 的能力放大器（VISION §11）
- "轻 ≠ 不行"：零依赖 1219 行核心，16 测试全绿，4+2 真实场景

## [0.1.0] - 2026-08-10

### 新增
- 项目骨架：pyproject.toml（零第三方依赖）、README、LICENSE(Apache-2.0)、NOTICE
- `solo/` 包：本体优先方法论 Agent 的最小闭环
  - `provider.py`：模型分层抽象（本地 ornith / 远端 DeepSeek / 嵌入 nomic），
    分级退出码（0-5），云端无 key 明确报错
  - `memory.py`：三层两域记忆（热域画像/温域事实+场景/冷域会话），
    Obsidian Markdown 导入导出，零依赖
  - `ontology.py`：本体建模（CSV→实体-关系-属性三元组，本体优先差异化核心）
  - `skill.py`：可复用经验提取（触发词/版本/步骤，跨轨迹抽象浅层）
  - `writing.py`：六维中文写作检查 D1-D6（正确性fail/风格warn）
  - `code.py`：代码影响分析 impact()（符号/依赖/反向依赖）
  - `task.py`：任务状态控制面（断点续跑/决策门/可证伪预期）
  - `agent.py`：循环五态最小实现（记忆装载+skill注入+推理+记忆提交）
  - `cli.py`：solo init/run/skill-add/import-obsidian/export-markdown/version
- `provider.yaml.example`：模型配置模板（key 从环境变量读，不入仓库）
- `tests/`：pytest 冒烟套件（13 项，覆盖全部模块 + 工厂本体关系建模）
- `examples/`：一人公司 4 个真实场景（写推文/查知识/开源检查/工厂本体建模）
- `.github/workflows/ci.yml`：轻量 CI（Python 3.9/3.11 + pytest）

### 修复
- memory 去重失效：add_fact 未存 h 字段导致重复写入，现已存
- provider 连接错误未分级：裸 ConnectionResetError 崩溃，统一捕获分级报 EXIT_NETWORK
- code 影响分析 import 解析：`from x import b` 跨行贪婪吞名 + 未解析到被 import 模块

### 方法论
- VISION.md：40 章节完整蓝图（本体优先 + 三层两域 + harness 工程 + 竞品定位）
- 差异化：本体优先（ibl.ai 证实 RAG 缺失层）；轻 ≠ 不行（工程极简非能力阉割）
