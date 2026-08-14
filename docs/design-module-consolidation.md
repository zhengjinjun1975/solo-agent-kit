# solo-agent-kit 整体模块合并整合设计

版本: 0.5.6 → 目标 0.6.x
日期: 2026-08-14
原则: **代码极简 + 架构完整 + 科学性**（单一事实来源 / 清晰依赖 / 无循环 / 不过度设计）

> 本设计仅基于实际代码分析产出。**只做设计，不改代码**；确认后再执行。
> 所有合并/新增均给出「省在哪」与「为什么更好」，避免为了"结构好看"而过度抽象。

---

## 0. 现状事实核查（设计依据，非推测）

基于逐文件通读 + 依赖图 + 死代码扫描，确认任务给的已知问题全部属实，并补充关键证据：

| 现象 | 证据 |
|---|---|
| 入口三处重复实现同一业务 | ① 环境检查：`cli._setup`(cli.py:243)、`web_api.setup_checks`(web_api.py:149)、`diagnostics.check_environment`(diagnostics.py:16) 三份几乎逐字相同的 Ollama/Python/config/记忆库检查。② 数值列探测：`cli._factory_stats`(cli.py:296)、`web_api.handle_stats`(web_api.py:229)、`web_server` do_GET:185 / do_POST:385 内联，四处各写一遍。③ 配置脱敏：`cli._config`(cli.py:267)、`agent.run` config 分支(agent.py:147)、`web /api/config` 各一份。 |
| registry.py 空转 | `@capability` 装饰器**零实际使用**。唯一消费是 `registry.capabilities()`，但 web_server 同时维护自己的硬编码 `CAPABILITIES` 字典(web_server.py:37)，`registry._init_defaults` 里 handler 全是 `lambda` 空壳。**两套能力清单并存，registry 是假抽象。** |
| 大量死代码 | `web_api.handle_memory_search / handle_stats / handle_ontology / setup_checks` **未被 web_server 调用**（web_server 自己内联了 stats 逻辑，handle_* 是孤儿）。其余死函数（只在自己文件出现、无人 import）：`gen.review_code`、`stats.correlation`、`stats.describe_stream`、`monitor.device_connect/top_processes`、`remote.remote_exec/deploy`、`netscan.scan_*` 等 17+ 个。 |
| code 4 模块职责重叠 | `code_review.py`(341) 已是静态分析**单一事实来源**（code.py / code_agent.py 都 import 它）。`code.py`=CodeGraph 影响分析，`code_agent.py`=CodeAgent 生成/审查/测试，`gen.py`=模型生成，其中 `gen.review_code` 与 `code_agent.review` 重叠。 |
| survey 已存在但未打通 | `factory/survey.py`(369 行) 已在，且被 `factory/__init__` import；但 cli/agent/web **零引用**，是一块没接入入口的孤岛能力。 |
| 依赖图（现状） | 无循环。但入口层 `cli→factory`、`agent→factory`、`web→factory` 各自直接 import domain，是重复的源头。 |

模块计数：solo 根 22 + factory 10(含 survey) + plugins 5 = **37 个 .py**。任务口径 33（不含 `__init__.py` 若干）。

---

## 1. 目标分层架构

```
┌─────────────────────────────────────────────────────────────┐
│ Interface（入口，只做"取参→分发→序列化"，零业务逻辑）          │
│   cli.py           命令行（argparse 解析 + 薄分发）           │
│   web_server.py    HTTP（路由 + 静态文件 + CORS，薄壳）        │
├─────────────────────────────────────────────────────────────┤
│ Application（编排/服务门面，业务聚合 + 跨域调用）              │
│   app.py           统一服务门面（clean/stats/audit/config/   │
│                    setup/report/capabilities）★ 新建          │
│   agent.py         AI 意图路由 + 对话编排                      │
│   task.py          任务/工单状态机（外置状态，断点续跑）        │
├─────────────────────────────────────────────────────────────┤
│ Domain（纯能力，无 HTTP/CLI 意识，只依赖 Infrastructure/同级） │
│   个人套件  memory.py / skill.py / writing.py(+zh_ai_taste)   │
│   代码套件  code_review.py(原子) + code.py(图+Agent+生成)     │
│   FDE 域    factory/data.py(clean+stats+audit)               │
│             factory/ontology.py / diagram.py(新增)           │
│             factory/survey.py / decisions.py / industry.py   │
│             factory/assist.py / ops.py(remote+monitor+site)  │
├─────────────────────────────────────────────────────────────┤
│ Infrastructure（地基，零业务，仅标准库）                       │
│   base.py          日志/原子写/锁/错误/数值工具(吸收 _util)   │
│   provider.py      模型分层 + 配置读写 + 脱敏(吸收 desensitize)│
│   data_connector.py 数据源(csv/db/sqlite/xlsx)                │
├─────────────────────────────────────────────────────────────┤
│ Plugins（可选扩展，独立交付面，不进入核心依赖）                │
│   excel_report / obsidian / visualize / netscan (+__init__)  │
└─────────────────────────────────────────────────────────────┘
```

**依赖方向（单一方向，无循环）**：Interface → Application → Domain → Infrastructure。Plugins 只依赖 Domain/Infrastructure，永不反向。

---

## 2. 合并整合方案（33 → 26）

> 设计规则：**合并的唯一判据是"同一概念域 + 共享高频原语"**。共享了 `is_num/quantile/guess_type/数值列探测` 才合并；只是同层就叫"套件"的（如 memory/skill）不硬塞。

### 2.1 入口层统一（最大收益）— 新建 `app.py`，cli/web 变薄壳

**合并**：web_api.py(280) 整体 → 吸收进新 `app.py`；cli.py / web_server.py 的重复业务逻辑全部下沉到 `app.py`。

**app.py 提供的服务门面（每个都是现存的重复点，收敛成一个）**：
- `app.data_clean(rows, **kw)` — 来源 cli._factory_clean + web 内联
- `app.data_stats(rows, col=None)` — **内含唯一数值列探测**，来源 cli._factory_stats + web_api.handle_stats + web 两处内联
- `app.data_report(rows, cols)` — 来源 web_api.build_report(102)
- `app.config_view()` — **唯一脱敏配置视图**，来源 cli._config + agent.config 分支 + web /api/config
- `app.check_environment()` / `app.deploy()` — 来源 diagnostics.check_environment + web_api.setup_checks/deploy（`check_environment` 收敛于此，删 diagnostics.py）
- `app.capabilities()` — **唯一能力清单**（取代 web_server 硬编码 dict + registry，删 registry.py）
- `app.build_ontology(rows, body)` — 来源 web_api.handle_ontology

**代价/收益**：
- `cli.py` 443→约 200（只剩 argparse 解析 + 一行调 app）
- `web_server.py` 760→约 420（只剩 HTTP 路由 + 静态服务，业务全调 app）
- 净省约 **350+ 行重复**，且修掉"改一处别的入口不生效"的隐性 bug（如数值列探测逻辑在 cli 和 web 各写了一遍、行为还不一致）
- **为什么架构更好**：入口从此只做 IO，业务逻辑单一事实来源；新增一个入口（如 API 网关）只需调 app，不再复制业务。

### 2.2 删 `registry.py`（假抽象）

**合并**：能力清单收敛为 `app.capabilities()` 一个 dict。删 registry.py(63)。
- **省**：63 行 + 移除一个没人用的装饰器机制 + 消除"web_server 硬编码 dict 与 registry 两份清单"的事实冲突
- **为什么**：`@capability` 零使用 = 过度设计。当唯一消费者只有"web 返回清单"这一个时，一个 dict 常量就够，不需要注册表。**等真出现"多个入口动态生成能力清单"的需求再加回**，现在加就是 YAGNI 违规。

### 2.3 code 4 模块 → 2 模块

**合并**：`code_agent.py`(306) + `gen.py` 的代码生成部分 → 并入 `code.py`(221)；`gen.py` 剩余文档生成 → 归 writing 域。`code_review.py`(341) 保留为**静态分析原子事实来源**。

```
code_review.py   静态分析（语法/复杂度/安全/评分）——唯一事实来源，KEEP
code.py          CodeGraph(影响分析) + CodeAgent(生成/审查/测试) + generate_code
                 ← 吸收 code_agent.py、gen.py 的 generate_code/review_code
```
- **省**：code_agent.py 里 `_static_analyze` / `_static_*` 兼容别名(code_agent.py:44-68) 是纯转发壳，合并后删除；`gen.review_code` 与 `code_agent.review` 重叠，删一处。净省约 **180 行**。
- **为什么**：三者本就共享 code_review 作单一事实来源，只是用 import 缝在一起。合并成一个 `code.py` 代码能力面，消除"生成/审查/影响分析"三处入口。

### 2.4 写作套件合并：`writing.py` + `zh_ai_taste.py`

**合并**：zh_ai_taste.py(160) → 并入 writing.py(303)。二者是同一"六维中文写作检查"概念域的两个切片。
- **省**：去掉 cross-import 的 `from solo import zh_ai_taste`，约 20 行胶水；`format_ai_taste`(writing) 与 zh_ai_taste 内部格式化重叠
- **为什么**：单一"写作检查"入口，而不是"写作 6 维 + 另一个人味检查"两个模块。若坚持分，纯属切分错误（不是同一粒度）。

### 2.5 工厂数据域合并：clean + stats + 新增 audit → `factory/data.py`

**合并**：`clean.py`(171) + `stats.py`(156) + 新增 `audit.py` → 合并为 **`factory/data.py`**。

这是"数据审视"的完整能力：清洗(clean) + 分析(stats) + 盘点/字典/质量(audit)。
- **省**：clean/stats/audit 三者共享 `is_num/quantile/guess_type/数值列探测`——现状是各在模块里 import `_util` 再自行拼装。合并后一次实现，且 `web_api.build_report`（数据概览=盘点+字典+质量的原型）直接归入 audit，不再跨层。
- **为什么**：三者是同一个概念域（对 rows 做审视），且 audit 的"盘点/字典/质量"本就由 clean.report + stats.describe 拼出来的（web_api.build_report 已验证）。分三个文件是人为切分。
- **audit.py 明确职责**（新增，融入 data.py）：
  - 盘点：`audit.schema(rows)` → 列名/类型/样本/唯一值
  - 字典：`audit.dictionary(rows)` → 字段中文名/口径/枚举值
  - 质量：`audit.quality(rows)` → 缺失/重复/异常/类型漂移
  - `audit.report(rows)` → 一键全量数据审视报告（吸收 web_api.build_report）

### 2.6 现场运维合并：remote + monitor + site → `factory/ops.py`

**合并**：`remote.py`(169) + `monitor.py`(128) + `site.py`(125) → `factory/ops.py`。
- **证据**：remote 与 monitor 都 import `site.py`（site 是现场/站点信息载体）；三者同属"FDE 现场运维"概念域。
- **省**：~90 行胶水；且 `remote.remote_exec/deploy`、`monitor.device_connect/top_processes` 是死函数，一并清理。净省约 **120 行**。
- **为什么**：一个"现场运维"能力面（连站点 + 采资源 + 远程执行），而非三个孤立小模块互相 import。

### 2.7 Infrastructure 小合并

- `_util.py`(25) → 并入 `base.py`（is_num/quantile 本就是 base 的数值工具）
- `desensitize.py`(113) → 并入 `provider.py`（配置脱敏是 provider 配置读写的一部分；`app.config_view` 调它）
- `diagnostics.py`(34) → 并入 `app.py`（check_environment 收敛为 app 方法）
- **为什么**：都是"同一个概念域内的一页纸函数"，独立成文件只会增加 import 跳转，不增加内聚。

---

## 3. 新增 FDE 交付产物层（survey / audit / diagram）融入

FDE 交付产物 = 「需求→验收 / 数据→审视 / 知识→图件」三条交付链，全部落在 **factory 域**，形成与闭源收拢对称的开源交付面：

```
factory/
  survey.py     需求→验收生命周期   (已存在 369 行，需接入入口)
  data.py       数据审视(盘点/字典/质量)  (clean+stats+audit 合并)
  diagram.py    图件(ER图/流程图)   (新增，消费 ontology/survey/task)
  decisions.py  声明式决策引擎      (已存在)
  ontology.py   本体建模           (已存在)
  industry.py   行业联动           (已存在)
  assist.py     FDE 起草辅助       (已存在)
  ops.py        现场运维           (remote+monitor+site 合并)
```

**三者的系统整体关系（依赖方向，无循环）**：
```
survey.py ──验收清单──→ plugins/excel_report.acceptance_report(出 xlsx)
    │
    ├─(需求条目)──→ diagram.py 流程图(FDE 交付链路可视化)
    │
ontology.py ──实体关系──→ diagram.py ER图
    │
survey/ontology ──质量校验──→ writing.py(中文质量自检, 已依赖)
data.py(质量报告) ──输入──→ audit 前置判断(数据可建模性)
```

- **survey.py**：已存在，唯一工作是**打通入口**——在 `app.py` 暴露 `survey_outline / survey_structure / survey_srs / survey_acceptance`，cli 加 4 个命令，agent 加 2 个意图，web 加 2 个端点。零新增算法。
- **diagram.py**（新增，~120 行）：纯展示层，消费已有数据（ontology.triples、survey PHASES、task.STATES），产出 ER 图 / 流程图（SVG 文本或 Mermaid 代码串，零第三方依赖，对齐已有 svg-info-diagrams 方法论）。**不新增数据模型**，只做"已有知识 → 图件"的序列化。
- **audit.py**：不是独立模块，**合并进 factory/data.py**（见 2.5），因为它的能力就是 clean+stats 的聚合，独立成文件反而制造跨模块依赖。

---

## 4. 极简原则核对（防止过度设计）

每个决定都先回答"现状有没有这个需求"，没有就不做：

| 决定 | 是否过度设计？ |
|---|---|
| 建 app.py 门面 | ✅ 必要——三入口重复是实测事实，收敛成单一事实来源 |
| 删 registry.py | ✅ 必要——零使用 = 死抽象；YAGNI 明确说删 |
| 合并 code 4 模块 | ✅ 必要——三处都 import 同一 code_review，合并是自然收敛 |
| 合并 data.py(clean+stats+audit) | ✅ 必要——共享全部数值原语 + audit 本就是两者聚合 |
| 合并 zh_ai_taste→writing | ✅ 必要——同一概念域切两半是错的 |
| 合并 ops.py(remote+monitor+site) | ⚠️ 边缘——三者确实同域，但若想保留 FDE 运维为独立插件面可暂缓（P2） |
| 合并 _util→base / desensitize→provider | ✅ 必要——一页纸函数独立成文件无收益 |
| 新增 diagram.py | ✅ 新增交付能力，非重构；低风险纯新增 |

**明确不做**（避免过度设计）：
- 不引入插件注册机制（plugins 保持朴素 import，等真有动态加载需求再加）
- 不把 app.py 拆成接口+实现的抽象层（一个门面足够，不要两层）
- 不统一 factory 与 personal 两套件为一个（这是产品边界，不是代码冗余）
- 不给 code_review / ontology 再套抽象基类（现状直接调用，无需 polymorphism）

---

## 5. 优先级（P0 先做 / P1 结构 / P2 增量）

### P0 — 高风险高价值，先做（可独立验收）
1. **建 `app.py` 服务门面 + cli/web 薄壳化**
   - 收敛：数值列探测 / Ollama检查 / 配置脱敏 / clean / stats / 数据概览
   - 验证：cli `factory-stats`、web `/api/stats`、agent `stats` 三入口输出一致
2. **删 `registry.py`**，能力清单收敛为 `app.capabilities()`（web_server 硬编码 dict 为唯一来源）
3. **删 web_api 死函数**（handle_memory_search/handle_stats/handle_ontology/setup_checks 等），其功能已被 app 门面覆盖
   - 低风险，可独立执行

### P1 — 中风险，结构性重组
4. **code 4 模块 → code.py + code_review.py**
5. **clean + stats + 新增 audit → factory/data.py**（audit 盘点/字典/质量）
6. **zh_ai_taste → writing.py**
7. **survey.py 接入入口**（app 暴露 + cli 命令 + agent 意图 + web 端点）

### P2 — 低风险，增量收尾
8. **remote+monitor+site → factory/ops.py**（可暂缓，若想保留运维独立面则跳过）
9. **_util → base.py、desensitize → provider.py、diagnostics → app.py**
10. **死代码清理**（gen.review_code、stats.correlation/describe_stream、monitor.device_connect/top_processes、remote.remote_exec/deploy、netscan.scan_* 等）
11. **新增 diagram.py**（ER图/流程图，纯新增低风险）

> 每步独立可测：合并后跑 `pytest`（现有 tests/）+ 对 cli/web/agent 三入口做行为等价抽测。P0 完成即已消除最大重复；P1 是结构收口；P2 是锦上添花。

---

## 6. 科学性：合并后的单一事实来源 / 依赖 / 无循环

### 6.1 单一事实来源清单（每个概念只有一个实现）

| 概念 | 唯一实现位置 | 现状（多份） |
|---|---|---|
| 数值列探测 | `app._detect_numeric_col` | cli / web_api / web_server×2 / agent |
| 环境检查 | `app.check_environment` | cli._setup / web_api.setup_checks / diagnostics |
| 配置脱敏视图 | `app.config_view` | cli._config / agent.config / web /api/config |
| 能力清单 | `app.capabilities` | web_server CAPABILITIES dict / registry.capabilities |
| 代码静态分析 | `code_review._static_analyze` | 已是(code/agent/gen 均指向它)✅ |
| 数值统计 | `factory.data` (原 stats) | cli/web/agent 各自拼 |
| 数据清洗 | `factory.data` (原 clean) | cli / web / agent 各自拼 |
| 数据概览报告 | `factory.data.audit.report` | web_api.build_report |
| 需求→验收 | `factory.survey` | 唯一，但未接入✅(改) |
| 任务状态机 | `task.py` | 唯一✅ |

### 6.2 依赖方向检查（无循环）

合并后依赖只向下：
```
cli.py ──→ app.py ──→ factory.data / factory.ontology / factory.survey / code / memory / skill
web_server.py ──→ app.py ──→ (同上)
agent.py ──→ app.py ──→ (同上) + provider
factory.diagram ──→ factory.ontology / factory.survey / task   (向下/同级)
factory.survey ──→ factory.industry / factory.assist / writing / task / plugins.excel_report
plugins.* ──→ factory.* / writing / ontology                     (只消费，不反向)
```
- **无环保证**：Domain 模块不 import Interface(app/cli/web_server)；app 不 import cli/web_server；diagram 只读下级数据不反向。现状唯一的准环（agent→web）已由 diagnostics 下沉解决，本次彻底收敛进 app。
- **删 registry 后**，agent/web 不再 import registry，消除一个"谁初始化谁"的隐性顺序依赖。

### 6.3 合并后模块清单与代码量预估

| 层 | 模块 | 来源 | 预估行数 |
|---|---|---|---|
| Infra | base.py | base + _util | ~150 |
| Infra | provider.py | provider + desensitize | ~560 |
| Infra | data_connector.py | 原样 | ~317 |
| Domain | memory.py / skill.py / writing.py | writing + zh_ai_taste | ~450 / 97 / 460 |
| Domain | code_review.py / code.py | code + code_agent + gen(code) | ~341 / ~460 |
| Domain | task.py | 原样 | ~195 |
| App | app.py | web_api + 入口重复业务 + registry清单 + diagnostics | ~300 |
| App | agent.py | 原样 | ~214 |
| Interface | cli.py / web_server.py | 薄壳化 | ~200 / ~420 |
| FDE | factory/data.py | clean + stats + audit | ~380 |
| FDE | factory/ontology.py | 原样 | ~456 |
| FDE | factory/survey.py | 原样(接入) | ~369 |
| FDE | factory/decisions.py / industry.py / assist.py | 原样 | ~251 / 224 / 340 |
| FDE | factory/diagram.py | 新增 | ~120 |
| FDE | factory/ops.py | remote + monitor + site | ~250 |
| Plugins | excel_report / obsidian / visualize / netscan | 原样 | ~455 |
| **合计** | **26 模块**（原 33/37） | | **~6700 行**（原 ~7330，净减 ~600，同时新增 audit/diagram 交付能力） |

> 33 → **26**：删 registry/diagnostics/desensitize/_util/site/web_api 6 个文件，zh_ai_taste/code_agent/gen 并入他处 3 个，remote+monitor 合并，clean+stats 合并；新增 audit(并入 data)、diagram 2 个能力。模块数与代码量双降，同时补上 FDE 交付产物层。

---

## 7. 交付风险与回滚

- **P0 第 1 步是最大改动**（入口重构），但它**纯收敛、不加行为**——三入口输出本来就该一致，现在只是把"四处各写一遍还互有出入"统一。用行为等价抽测兜底。
- 每步合并前先 `git tag` 或提交 checkpoint；合并后跑 `pytest` + cli/web 冒烟。
- survey/diagram/audit 是新增交付能力，与既有功能正交，失败不伤核心。

**结论**：33/37 模块收敛为 **26**，净减 ~600 行，同时新增 audit（数据审视）、diagram（图件）两项 FDE 交付能力；单一事实来源从"每概念 2-4 份"降为"每概念 1 份"；依赖单一向下无循环。先做 P0（入口收敛 + 删 registry/死代码），再做 P1（结构合并 + survey 打通），P2 增量收尾。
