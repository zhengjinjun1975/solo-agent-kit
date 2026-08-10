# Changelog

所有显著变更记录在此。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.7.5] - 2026-08-10

### 修复(技能库乱码数据)
- skill.all_details 过滤含 U+FFFD 替换字符的乱码技能(写入时编码损坏无法恢复)
- 清理真实技能库(index.json)中的乱码条目
- 4项ad-hoc验证通过, 43测试全绿

## [0.7.4] - 2026-08-10

### 修复(代码审查发现的SQL注入漏洞)
- data_connector SQL注入: _read_sqlite/_read_rdbms 表名拼接未白名单校验, 新增 _safe_table_name(仅允许字母数字下划线)彻底防注入
- 实测7种注入载荷(;DROP/OR 1=1/引号/;--/DELETE/注释)全部拦截, 12项验证通过
- 43测试保持全绿

## [0.7.3] - 2026-08-10

### 变更(基于原子库极简重构, 去重不改变行为)
- 新增 solo/_util.py 统一跨模块重复工具(is_num/quantile), 从原子库(D:/domain-libs/solo-atoms)复制极简实现
- 消除重复: stats(本地_num/_quantile)、clean(_isnum/_quantile)、cli(_num)、web_api(num) 全部统一到 _util
- 净减代码 ~36 行, 43 项测试保持全绿(行为不变)
- 保持零依赖独立(不从 domain-libs import, 复制源模式)
- 版本号同步(三处一致)

## [0.7.2] - 2026-08-10

### 变更(端到端测试套件 + 数据入库)
- tests/test_e2e.py: 19项端到端测试(对话/写作/代码/决策/清洗/分析/本体/技能/部署/配置/FDE监控日志浏览)
- 修复CI根因: examples/data数据文件入仓库(.gitignore的data/误忽略)
- 37项测试全绿(18单测+19e2e), CI绿

## [0.7.1] - 2026-08-10

### 变更(FDE现场能力)
- 工厂数据工作区UI卡片化(ds-card/全宽渐变主按钮)
- FDE-3远程运维: remote.py系统OpenSSH零依赖(连接/执行/部署/日志)
- FDE-4工单闭环: task.new_issue(triage自动分类)/diagnose/resolve_issue

## [0.7.0] - 2026-08-10

### 变更(FDE能力深化, 对标三体+FDE现场)
- 写作深化: 4风格模板(tweet/report/wechat/paper)+rewrite
- 代码深化: review代码审查(裸except/TODO)
- 决策深化: forecast/price_compare/supplier_score指标(8类决策)
- FDE-1环境监控: /api/monitor(psutil CPU/内存/磁盘/进程)
- FDE-2日志诊断: /api/logs(内存缓冲日志查看器)

## [0.6.0] - 2026-08-10

### 变更(CodeAgent审查P0+P1+P2修复)
- P0: 原子写+并发锁/日志系统/错误契约/SQL白名单/数据报告导出/多轮对话
- P1: 接口dataclass/解反向依赖/能力注册表/并发/记忆向量检索/LLM意图
- P2: 文档工程化/诚实化/备份恢复/xlsx/大数据流式/前端拆模块

## [0.5.5] - 2026-08-10

### 变更(UI美观度优化, 2026设计趋势)
- 字体呼吸: 抗锯齿/优化legibility/行高留白
- 层次微动效: 导航hover位移/按钮lift/卡片hover阴影
- 阴影柔化: --shadow-hover/边框减重(0.18→0.12)
- 渐变个性: logo渐变+hover旋转/消息渐变/按钮渐变
- 圆角统一16px, 输入框聚焦环

## [0.5.4] - 2026-08-10

### 变更
- 清理测试垃圾记忆(20→2条真实), 系统状态术语优化
- 导航图标针对性设计: 内联SVG替换通用方块
  - 工厂数据: 十字/折线图/实体网络图
  - 工作区: 笔/代码尖括号/星
  - 系统: 仪表盘/齿轮

## [0.5.3] - 2026-08-10

### 变更(模式/工作区式导航重构)
- 记忆移除独立入口(后台能力)
- 生成并入代码工作区
- 技能: skill库管理面板(增删改查)
- 写作: 写作工作区(文本+六维实时检查)
- 代码: 代码全栈工作区(库概览+生成)
- 配置: 完整配置面板(工具必需项)
- 部署: 系统环境检查面板
- 工厂数据: 选数据源→执行(激活流程)

## [0.5.2] - 2026-08-10

### 变更(小版本递增, 不跳大版本)
- 前端导航全部关联真实模块执行(不再摆设)
- 前端结果友好化(fmtResult替代裸JSON)
- agent补config/capabilities意图 + skill分支

### 版本规则
- 小版本+0.01递增, 不轻易跳大版本(除非用户主动要求)

## [0.5.1] - 2026-08-10

### 修复(OpenClaw审查P0)
- detect_anomaly 空数据/少数据防护(防IndexError)
- CodeGraph RE_DEF 支持缩进 → 方法级符号索引(39→110)
- agent chat兜底身份锚定(防模型自报Ornith)
- web_server CORS收窄到本地 + 路径参数白名单(防任意文件读)
- cli 退出码转译(未知命令2→1, 不与EXIT_NETWORK撞车)

## [0.5.0] - 2026-08-10

### 新增
- AI 原生对话路由：agent.py 意图识别→调用全部套件模块（自然语言指挥）
- Web 后端 web_server.py：完整 REST API（clean/stats/ontology/memory/skill/writing/code-overview/gen/setup/config）
- 前端重写为 AI 原生设计（OpenClaw 式聊天对话框为中心，WorkBuddy 多面板）
- provider.yaml 从文件读取真正生效

### 修复
- agent 兜底对话固定本地（不因 context 长误判走远端无key报错）
- web_server POST 异常返回 500 JSON（不静默）
- route 意图识别 9/9（memory_search 优先于 ontology）

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
