# solo-agent-kit — FDE 原子化架构（对齐 10 核心原子 + 写作原子）

> 项目：`本仓库根目录`
> 版本：当前 HEAD `c06e168`（完全原子化重构，10 核心原子真下沉 + kernels 纯算法）+ 写作原子落盘
> 参考：`_os/solo-fde-linkage-deepen.md`（深度补强）、`_os/fde-latest-tech-deepdive.md`（最新技术）
> 目标：描述当前 **10 核心原子 + 2 写作原子** 的真实架构，消除「文档宣称 15 原子 vs 代码 10 原子」脱节。

---

## 0. 一句话结论

> solo 方法论内核（本体优先 / 零依赖 / 开源边界）是稀缺资产。当前已完成**完全原子化重构**：
> FDE 监测/诊断/决策/本体/记忆/交付/写作能力拆成可独立运行、可被组装的原子，
> 纯算法下沉 `kernels/`，统一运行时 + 组装链（监测→诊断→写作→交付→验收）+ 自进化框架。
> **注册表实为 10 核心原子 + 2 写作原子（write-qa / write-evidence）**，写作已接入交付链。

---

## 1. 现状盘点与对齐

### 1.1 能力现状（当前 HEAD 实测）
| 域 | 实现模块 | 能力 | 原子 | 成熟度 |
|---|---|---|---|---|
| fde | `fde_runtime/` + `atoms/fde/` | 工单/状态机 | `fde-task` | ✅ |
| memory | `atoms/memory/` + `solo/memory.py` | 三层两域记忆 | `memory` | ✅ 强 |
| monitor | `atoms/monitor/` + kernels/monitor_stats | 采集/异常/阈值/协议 | `monitor-device` | ✅ |
| predict | `atoms/monitor/` + kernels/forecast | 趋势/RUL/风险 | `predictive-maintain` | ⚠️ 雏形(RUL线性) |
| ontology | `atoms/ontology/` + kernels/ontology_core | 本体/聚合问答/RAG | `ontology-qa` | ✅ |
| decision | `atoms/decision/` + kernels/rules | SME 决策 | `sme-decision` | ✅ |
| diagnose | `atoms/diagnose/` + kernels/memory_score | 故障知识库/防幻觉 | `diagnose-kb` | ✅ |
| deliver | `atoms/delivery/` + kernels/survey_core | 交付验收闭环 | `deliver-accept`(闭源) / `deliver-train` | ✅ |
| write | `atoms/writing/` + `solo/writing.py` | 六维写作/AI味 | `write-qa` | ✅ |
| evidence | `atoms/writing/` + `solo/factory/evidence.py` | 证据账本/事实核查 | `write-evidence` | ✅ |

> **本次对齐**：早期架构宣称 15 原子（含独立 `monitor-anomaly` / `factory-cognition` / `delivery-package`）。
> 经完全原子化重构，已**合并为 10 核心原子**（anomaly→monitor-device+predict-maintain、cognition→ontology-qa、package→deliver-accept），
> 并新增 **2 个写作原子**（write-qa / write-evidence）接入交付链。

### 1.2 回归基线
- `pytest tests/` **264 passed 全绿**（曾 240 passed / 21 failed，21 条为过期 linkage-deepen 测试，已重写对齐）。
- 组装链 `fde-workflow.json` 端到端全绿（含写作，`accept=True`、`loop_closed=True`）。

---

## 2. 原子化设计原则（对齐生态 + CodeAgent 范式）

> **原子智能体 = 一个能力、一个目录、一份 manifest、一个入口、可独立运行、可被组装。**
四条不变量：**A1 单一职责**（一原子一类能力，不做编排）/ **A2 自包含**（自己 manifest+入口+依赖声明）/
**A3 可独立运行**（`main.py` 的 `__main__` 独立可跑自证）/ **A4 可组装**（manifest 声明输入/输出/依赖供上层组合）。

---

## 3. 原子清单（10 核心 + 2 写作，共 12 原子）

| 域 | 原子名 | agent | 能力 id | 复用的现有模块/kernels |
|---|---|---|---|---|
| data | data-cap | data | `data.cap` | kernels/spc |
| memory | memory | memory | `memory.core` | solo/memory.py |
| fde | fde-task | fde | `fde.task` | solo/task.py |
| monitor | monitor-device | monitor | `monitor.device` | kernels/monitor_stats + forecast |
| monitor | predictive-maintain | monitor | `predict.maintain` | kernels/forecast + spc |
| ontology | ontology-qa | ontology | `ontology.qa` | kernels/ontology_core + memory_score |
| decision | sme-decision | decision | `sme.decision` | kernels/rules |
| diagnose | diagnose-kb | diagnose | `diagnose.kb` | kernels/memory_score + rules |
| deliver | deliver-accept | deliver | `deliver.accept` | kernels/survey_core（**唯一闭源**） |
| deliver | deliver-train | deliver | `deliver.train` | kernels/survey_core |
| **write** | **write-qa** | write | `write.qa` | solo/writing.py（六维 + AI味） |
| **write** | **write-evidence** | write | `write.evidence` | solo/factory/evidence.py（证据核查） |

**合并映射（15→10）**：`monitor-anomaly`→`monitor-device`+`predictive-maintain`；
`factory-cognition`→`ontology-qa`；`delivery-package`→`deliver-accept`。

---

## 4. 统一运行时（能力路由 / 依赖 / 冲突 / 降级）

- `fde_runtime/` 框架（纯标准库）：`base.py`（AtomicAgent 基类+状态机+信封+CapabilityRegistry）、
  `manifest.py`（schema 校验）、`loader.py`（扫描/注册表/依赖解析/load/run/降级）、`linkage.py`（联动）、`evolve.py`（自进化）。
- **能力路由**：`runtime.run_capability("monitor.device", **inputs)` → 经 `capability→atom` 索引找到提供原子 → `run`。
- **依赖/冲突**：拓扑排序（被依赖者先加载）、环检测、能力占用冲突检测、版本约束。
- **降级**：核心异常 → `{ok:false,error,degraded:true}`；可选依赖缺失不阻断（如 `deliver-accept` 闭源在开源链中 optional 降级）。

---

## 5. 组装链（fde-workflow.json，v2.0）

```
monitor.device → data.cap → predict.maintain → sme.decision → fde.task
 采集             SPC       预测/风险          决策          工单(when条件)
→ diagnose.kb → predict.maintain → write.qa → write.evidence → deliver.accept → deliver.train
   知识库          维修建议          六维写作     证据核查        交付验收(可选闭源)  培训
```

- `run_flow` 注入上游 `{ok,data}`，`$ref` 引用、`when` 条件、`optional` 降级。
- `final{worst_level, tickets_n, accept, writing_qa_fail, writing_evidence_pass}`。
- **写作步骤**：`write_qa`（六维扫描交付报告文本）→ `write_evidence`（证据账本 + 事实核查），实现「写作监测→诊断→写作报告→交付」闭环。

---

## 6. 边界（开源原子 + 闭源编排，数据不出厂）

- **开源原子**：算法/能力全开源（Apache-2.0），本地运行，数据不出厂。
- **闭源编排**：`deliver-accept` 为唯一闭源原子（`open_source:false`），开源原子禁依赖闭源原子（`check_open_source_boundary` 强制），开源组装链中 `optional` 降级。
- **数据不出厂**：原子本地 `data/` 存储；LLM 增强默认 `local_only=True`（安全默认值）。

---

## 7. 写作原子落盘

| 原子 | 能力 | op | 复用核心（加壳不改） |
|---|---|---|---|
| write-qa | `write.qa` | scan（六维D1-D6）/ ai_taste / styles | solo/writing.py |
| write-evidence | `write.evidence` | build_ledger / fact_check / report | solo/factory/evidence.py |

写作从「legacy `solo/writing.py` 单体函数」升级为**可被组装链调用的原子**，接入交付链写作环节。

---

## 8. 验证纪律

- 每个原子 `main.py` 的 `__main__` 独立可跑（A3 铁律自证）。
- 真实数据验证（非空壳）：原子 load/run、组装链 run_flow（含写作）、交付包、动态阈值、证据核查。
- 回归全绿：`pytest tests/ -q` **264 passed** + `tests/test_fde_linkage_deepen.py`（对齐 10 核心 + 写作）。
- 推送前 `git status` 检查泄漏（密钥/甲方数据/闭源）。

---

## 附：落地范围

1. `fde_runtime/` 原子框架（base/manifest/loader/linkage/evolve/cli）
2. `atoms/` 12 原子（10 核心真下沉 + write-qa + write-evidence）
3. `assemblies/fde-workflow.json` 组装链（含写作步骤）
4. `registry.json` 注册表（12 原子）
5. `tests/test_fde_linkage_deepen.py` 对齐回归（26 用例）
6. `_os/solo-fde-atomic-architecture.md` / `_os/solo-fde-linkage-deepen.md` 文档对齐
