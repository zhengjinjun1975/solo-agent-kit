# solo-agent-kit — FDE 原子化重构 + 优化详细方案

> 项目：`E:/open-source/solo-agent-kit`
> 版本：v0.6.0 提案（FDE 能力原子化重构）
> 参考：`_os/fde-latest-tech-deepdive.md`（最新技术）、生态原子化架构（域+原子/manifest/生命周期/组装器）、CodeAgent 原子化重构范式（16原子+统一运行时+入口+自进化）
> 目标：**提交 solo 优化详细方案 + FDE 能力提升 + 原子化重构 FDE 能力**（拆原子+统一运行时+组装链+自进化），细粒度可迭代，最大化沿用现有模块核心零改动。

---

## 0. 一句话结论

> solo 的方法论内核（本体优先 / 零依赖 / 开源边界）是稀缺资产，但"**能力到达率**"不足：FDE 监测/交付/写作等能力散落在单体模块、互相不可组装，最强项（本体问答/记忆/证据）没有形成可被甲方感知的**交付包闭环**。本次以 **原子化重构 + 组装链 + 自进化** 为主线：把 solo FDE 能力拆成可独立运行、可被组装的原子，用统一运行时 + 组装链（监测→诊断→交付→验收）+ 自进化（反馈→改进）把它们串成一个可谈钱、可迭代的端到端闭环，同时吸收最新技术（动态阈值 / 交付包闭环 / 协议升级）做 FDE 能力提升。

---

## 1. 现状盘点与 P0/P1 修复

### 1.1 能力现状盘点
| 域 | 实现模块 | 能力 | 成熟度 |
|---|---|---|---|
| fde | `factory/survey.py` | 需求访谈/结构化/SRS/验收清单/勾稽 | ✅ 方法论框架齐 |
| fde | `factory/assist.py` | 问题集/词典初稿/报告起草(D0/D1/D4) | ⚠️ 库函数为主 |
| fde | `task.py` | 工单状态机/审计轨迹/diagnose/验收 | ✅ 可用 |
| memory | `memory.py` | 三层两域记忆 + OptMem + skill | ✅ 强 |
| monitor | `factory/monitor.py` | MetricStore/AlertEngine/工单状态机/MQTT/MonitorAsk | ⚠️ P0 骨架缺深度 |
| protocols | `factory/protocols.py` | TCP行/HTTP直采 + MQTT/Modbus/OPC-UA(可选) | ✅ 设计好 |
| write | `writing.py` | 六维中文写作检查 / ai_taste | ⚠️ 规则稀疏 |
| evidence | `factory/evidence.py` | 证据账本/FactChecker 防幻觉 | ✅ 差异化 |
| ontology | `factory/ontology/` | 本体建模/聚合问答/语义 | ✅ 差异化核心 |
| delivery | `factory/assist.py::report_draft_dict` | 交付报告(结构化,对齐闭源 deliver) | ⚠️ 未闭环成可签收交付包 |

### 1.2 本次发现的 P0/P1（实测回归基线：`pytest tests/` 238 collected，2 failed）
| 级别 | 问题 | 现象 | 修复 |
|---|---|---|---|
| P0 | **memory P1 性能优化破坏了 support.KnowledgeBase 读契约** | `memory.py` 未提交改动把 `add_fact` 改为「追加日志+内存缓存」，但 `KnowledgeBase.all()` 仍 `_load(facts.json)`，日志未合并 → `len(all())==0`；`test_uses_memory_underlying` 同样读 `facts.json` 读到 0 | 让 `KnowledgeBase.all()` / 底层读取经 `Memory` 的**合并视图**（快照+日志），并保留 `_facts_path` 语义；回归转绿 |
| P1 | 交付产物未闭环 | SRS/资产盘点/质量诊断/报告多停留在库函数/设计稿，无「一键可签收交付包」 | delivery 域原子化，串现有模块成一键交付包（监测报告+工单+交付报告+验收清单） |

> 说明：`memory.py`/`data_connector.py` 有未提交改动（工作区脏），本次会先评估并纳入修复（P0 性能优化方向保留，仅修读契约）。

### 1.3 修复验证（回归全绿）
- 基线：238 collected / 236 passed / 2 failed。
- 目标：修复 P0 后 **pytest tests/ 全绿**，并新增原子化测试。

---

## 2. FDE 优化方案 P0 / P1 / P2（对标最新技术，细粒度可迭代）

> 原则：P0 = 高效益、中低投入、离线可交付、构成后续基础；P1 = 进阶智能；P2 = 规模化/先进。每一项都对应**一个可独立验证的原子或组装链环节**，不一次性推倒重来。

### P0（先落地，2-4 周量级）
1. **FDE 原子化重构（本次核心）**：把 fde/memory/monitor/protocols/write/evidence/ontology/delivery 拆成**可独立运行、可被组装**的原子（现有模块核心零改动 + manifest + main.py 壳），统一运行时 + 统一入口 + 组装链 + 自进化。→ 见 §3。
2. **交付包一键生成（G1）**：`delivery` 原子串现有模块成一键可签收交付包（监测快照+工单+交付报告+验收清单），`--json` 结构化对齐闭源 deliver。→ 见 §3.6。
3. **monitor 动态阈值（G2，最小卖点闭环）**：在 `AlertEngine` 之上新增**动态阈值**能力（MAD 稳健基线 + 自适应 k·std + 趋势/突变融合），替代纯静态阈值，降低误报/漏报。→ 见 §4.1。
4. **协议升级（G2 协议域）**：`protocols` 原子吸收最新技术——MQTT5 特性（User Properties / Message Expiry / Topic Alias）与 Sparkplug B 生命周期解析（NBIRTH/DBIRTH/DATA/DEATH → 自动登记设备上/离线）的**能力接口 + 明确缺库报错**。→ 见 §4.3。
5. **验收闭环（G1）**：组装链末端「验收」环节，需求跟踪矩阵/验收清单勾稽 → 交付报告可签收。

### P1（进阶智能，+2-4 周）
1. **故障知识库闭环（G5）**：monitor 告警 + memory 沉淀 → 运维知识库（问题→解决）自闭环。
2. **监测可视化**：monitor 数据管道出看板（WebSocket 推 latest/alerts）。
3. **离线 RAG 知识库**：ontology 确定性问答 + 非结构化文档语义检索（bge-m3/LanceDB 可选）。
4. **写作品质升级**：writing 六维检查规则扩充 + 证据核查联动。
5. **自进化增强**：反馈→改进回灌（阈值/词典/规则真正改写，见坑㉝）。

### P2（规模化/先进，视需要）
1. **多租户知识库注册**（对齐生态多租户本体注册表）。
2. **移动端 / 离线作业最小集**。
3. **边缘网关部署 / 行业模板库**。
4. **闭源交付增值层**（订阅/买断）。

---

## 3. FDE 原子化重构（本次实施核心）

### 3.1 设计原则（对齐生态原子化架构 + CodeAgent 范式）
> **原子智能体 = 一个能力、一个目录、一份 manifest、一个入口、可独立运行、可被组装。**
四条不变量：**A1 单一职责**（一原子一类能力，不做编排）/ **A2 自包含**（自己 manifest+入口+依赖声明）/ **A3 可独立运行**（不依赖编排者也能单跑）/ **A4 可组装**（manifest 声明输入/输出/依赖供上层组合）。

### 3.2 域划分 + 原子清单
| 域 | 原子名 | agent 类型 | 能力 id | 复用的现有模块（零改动） |
|---|---|---|---|---|
| fde | fde-task | fde | `fde.task` | `solo/task.py`（工单状态机/诊断/验收） |
| monitor | monitor-metric | monitor | `monitor.metric` | `solo/factory/monitor.py::MetricStore` |
| monitor | monitor-alert | monitor | `monitor.alert` | `solo/factory/monitor.py::AlertEngine` + **动态阈值增强** |
| monitor | monitor-protocol | monitor | `monitor.protocol` | `solo/factory/protocols.py`（TCP/HTTP/MQTT/Modbus/OPC-UA） |
| monitor | monitor-ask | monitor | `monitor.ask` | `solo/factory/monitor.py::MonitorAsk`（问数） |
| memory | memory-fact | memory | `memory.fact` | `solo/memory.py::Memory`（三层两域） |
| memory | memory-optmem | memory | `memory.optmem` | `solo/memory.py::optmem_note/search` |
| write | write-qa | write | `write.qa` | `solo/writing.py`（六维检查/ai_taste） |
| write | write-evidence | write | `write.evidence` | `solo/factory/evidence.py`（证据账本/FactChecker） |
| ontology | ontology-qa | ontology | `ontology.qa` | `solo/factory/ontology/`（建模/问答） |
| delivery | delivery-package | deliver | `delivery.package` | `solo/factory/assist.py::report_draft/dict` |

**每个原子 = 现有模块核心零改动 + `manifest.json` + `main.py`（壳）**，壳 import 并调用现有核心，包 `{ok,data}` 信封。

### 3.3 统一运行时（能力路由 / 依赖 / 冲突 / 降级）
- `fde_runtime/` 框架（纯标准库）：`base.py`（AtomicAgent 基类+状态机+信封+CapabilityRegistry）、`manifest.py`（schema 校验）、`loader.py`（扫描/注册表/依赖解析/load/run/降级）。
- **能力路由**：`runtime.run_capability("monitor.alert", **inputs)` → 经 `capability→atom` 索引找到提供原子 → `run`。
- **依赖/冲突**：拓扑排序（被依赖者先加载）、环检测、能力占用冲突检测、版本约束。
- **降级**：核心异常 → `{ok:false,error,degraded:true}`；可选依赖缺失不阻断，运行期跳过。

### 3.4 统一入口 + 组装链（fde 工作流：监测→诊断→交付→验收）
- **统一入口**：`fde_runtime/cli.py` 命令 `scan/registry/status/run/chain/evolve/capabilities`。
- **组装链** `assemblies/fde-workflow.json`：`monitor.metric → monitor.alert → fde.task(诊断/工单) → delivery.package → 验收`。
  `run_flow` 把上游 `{ok,data}` 输出注入下游端口，拓扑序逐原子 run，产出一条**可溯源链路 trace** 与 `final{worst_level, tickets, report, accept}`。

### 3.5 自进化（反馈→改进）
- `fde_runtime/evolve.py`：反馈闭环——`evolve(observation)` 记录反馈 → 归因 → 改进（动态阈值/词典/规则）→ 校验 → 沉淀记忆。`loop_closed` 由各环节真实结果计算（不无条件 True，见坑㉜）。

### 3.6 边界（开源原子 + 闭源编排，数据不出厂）
- **开源原子**：算法/能力全开源（Apache-2.0），本地运行，数据不出厂。
- **闭源编排**：编排/交付增值层归闭源（对齐 `_closed/orchestrator`），开源原子禁依赖闭源原子（`check_open_source_boundary` 强制）。
- **数据不出厂**：原子本地 `data/` 存储；LLM 增强默认 `local_only=True`（安全默认值，见坑重组合③）。

---

## 4. FDE 能力提升（吸收最新技术）

### 4.1 动态阈值（monitor-alert 增强，P0 最小卖点闭环）
- 参考 `fde-latest-tech-deepdive.md §2.2`：在静态阈值上叠加**层1 统计基线**（零依赖先上线）：MAD 稳健基线 + 自适应 k·std + 趋势/突变融合。
- `AlertEngine` 保持原语义，新增 `adaptive_threshold(series, k)` 动态计算阈值 → 告警复用现有工单闭环，`type="adaptive"`。
- 真实数据验证：用带漂移的时序验证动态阈值比静态阈值**误报/漏报更低**。

### 4.2 交付包闭环（delivery-package）
- 把 `report_draft_dict` 串成完整交付包：监测快照 + 工单 + 交付报告 + 验收清单 + 签收状态，`--json` 结构化可被闭源 deliver 消费（`solo_draft:true` 标记）。

### 4.3 协议升级（monitor-protocol）
- MQTT5 特性接口（User Properties / Message Expiry / Topic Alias）+ Sparkplug B 生命周期解析能力接口，缺库明确报错（保持零依赖降级）。
- `protocols()` 能力自省，返回支持的协议清单。

### 4.4 其他
- 记忆自进化（OptMem 语义检索）、写作+证据防幻觉联动、本体确定性问答扩展。

---

## 5. 商业化（细粒度可迭代）

- **定价**：开源免费（获客/信任）+ FDE 人天（普通 3-6k / 高级 6-12k）+ 交付增值闭源（订阅/买断）。
- **核心策略：卖结果不卖功能**。量化价值锚点：非计划停机损失 12.6%（IDC）、预测性维护停机 ↓63.8%、动态阈值误报率 ↓61%。
- **对标竞品**：通用 Agent 框架 / 工业本体平台 / 物联网监测平台 / SaaS MES / Palantir 式。我们胜在：零依赖、离线、本体优先、可嵌入、可被甲方自持。
- **商业模式**：Open-Core（算法开源 + 交付增值闭源）+ 三阶段收入（服务→软件→平台）。

---

## 6. 验证纪律
- 每个原子 `main.py` 的 `__main__` 独立可跑（A3 铁律自证）。
- 真实数据验证（非空壳）：原子 load/run、组装链 run_flow、交付包、动态阈值。
- 回归全绿：`pytest tests/ -q` 全绿 + 新增 `tests/test_fde_atomic.py`。
- 推送前 `git status` 检查泄漏（密钥/甲方数据/闭源）。

---

## 附：本次落地范围（可迭代切片）
1. `_os/solo-fde-atomic-architecture.md`（本文档）
2. `fde_runtime/` 原子框架（base/manifest/loader/runtime/cli/evolve）
3. `atoms/` 11 原子（现有模块核心零改动 + manifest + main.py 壳）
4. `assemblies/fde-workflow.json` 组装链
5. `registry.json` 注册表
6. `tests/test_fde_atomic.py` 原子化验证 + P0 修复 + 回归全绿 + 推送
