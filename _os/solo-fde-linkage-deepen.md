# solo FDE 深度补强（对齐 10 核心原子 + 写作原子）

> 说明：本文档已随 `c06e168`（完全原子化重构，10 核心原子真下沉 + kernels 纯算法）与写作原子落盘对齐。
> 早期「15 原子 + monitor-anomaly/factory-cognition/delivery.package 独立原子」架构已合并为 10 核心原子，并新增 write-qa / write-evidence 两个写作原子。
> 仓库：`E:/open-source/solo-agent-kit`

---

## 1. 背景：原子化收敛 + 深度补强

`solo-agent-kit` 完成**完全原子化重构**：把早期散落的 15 个原子（含 `monitor-anomaly` / `factory-cognition` / `delivery-package` 独立原子）收敛为 **10 核心原子**，纯算法下沉到 `kernels/`（monitor_stats / forecast / spc / ontology_core / memory_score / rules / survey_core），原子只做 op 分发 + IO + 状态。

**合并说明**：
- `monitor.anomaly`（时序异常 + RUL）→ 并入 `monitor.device`（异常检测）+ `predict.maintain`（预测性维护 RUL）。
- `factory.cognition`（本体问答 + 离线 RAG）→ 并入 `ontology.qa`（本体建模/聚合问答/知识检索）。
- `delivery.package`（一键交付包）→ 并入 `deliver.accept`（需求→SRS→验收→勾稽→交付包→签收）。

**写作原子落盘**：把 legacy `solo/writing.py`（六维 D1-D6 中文写作检查 + AI 味自检）与 `solo/factory/evidence.py`（证据账本 + 事实核查防幻觉）加壳为两个原子，接入交付链：
- `write-qa`（能力 `write.qa`）：六维中文写作质量检查 + AI 味自检。
- `write-evidence`（能力 `write.evidence`）：证据账本 + 事实核查（防幻觉、可溯源）。

---

## 2. 10 核心原子 + 2 写作原子

| 原子 | 能力 | agent | 复用来源 | 说明 |
|------|------|-------|----------|------|
| data-cap | `data.cap` | data | kernels/spc | 清洗/SPC/CPK/描述统计/趋势/报告 |
| memory | `memory.core` | memory | solo/memory | 三层两域记忆 |
| diagnose-kb | `diagnose.kb` | diagnose | kernels/memory_score+rules | 故障知识库 add/search/suggest，诚实 miss |
| fde-task | `fde.task` | fde | solo/task | 工单状态机/审计轨迹/诊断 |
| monitor-device | `monitor.device` | monitor | kernels/monitor_stats+forecast | 采集/异常检测/动态阈值/告警/协议/问答 |
| predictive-maintain | `predict.maintain` | monitor | kernels/forecast+spc | 趋势预测/风险等级/RUL/维修建议 |
| ontology-qa | `ontology.qa` | ontology | kernels/ontology_core+memory_score | 本体建模/聚合问答/知识检索(RAG) |
| sme-decision | `sme.decision` | decision | kernels/rules | SME 决策/阈值表 |
| deliver-accept | `deliver.accept` | deliver | kernels/survey_core | 【唯一闭源】交付验收闭环（需求→SRS→验收→勾稽→交付包→签收） |
| deliver-train | `deliver.train` | deliver | kernels/survey_core | 培训材料 |
| **write-qa** | **`write.qa`** | write | solo/writing | 六维 D1-D6 中文写作质量检查 + AI 味自检 |
| **write-evidence** | **`write.evidence`** | write | solo/factory/evidence | 证据账本 + 事实核查（防幻觉、可溯源） |

**边界铁律**：联动传「算法入参」，各原子数据本地自持（data/），**数据不出厂**；开源原子禁依赖闭源原子（`loader.check_open_source_boundary`）；唯一闭源 `deliver-accept` 在开源组装链中为 `optional` 降级。

---

## 3. 组装链（fde-workflow.json，v2.0 端到端全绿含写作）

```
monitor.device → data.cap → predict.maintain → sme.decision → fde.task → diagnose.kb
 采集             SPC       预测/风险          决策          工单         知识库
→ predict.maintain → write.qa → write.evidence → deliver.accept → deliver.train
   维修建议            六维写作     证据核查        交付验收(闭源可选)   培训
```

`run_flow` 把上游 `{ok,data}` 注入下游端口，`$ref` 引用、`when` 条件、`optional` 降级。产出 `trace` 与 `final{worst_level, tickets_n, accept, writing_qa_fail, writing_evidence_pass}`。

**实测**：`pytest tests/` **264 passed 全绿**；组装链端到端 `accept=True`、`loop_closed=True`，写作步骤（write-qa 六维扫描 + write-evidence 证据核查）真实执行。

---

## 4. 写作原子落盘（write-qa / write-evidence）

### write-qa（能力 `write.qa`）
- `op=scan`：六维 D1-D6 中文写作质量检查（D1错字/D2标点/D3语病/D4数字/D5去AI味/D6活人感），返回 `report{passed, fail_count, layers}`。
- `op=ai_taste`：AI 味自检（分 100=最像人 + 可执行改写建议）。
- `op=styles`：可用写作风格清单（tweet/report/wechat/paper）。
- 复用 `solo/writing.py` 核心，加壳不改核心。

### write-evidence（能力 `write.evidence`）
- `op=build_ledger`：从文本提取证据账本（数字/百分比/极值/日期声明）。
- `op=fact_check`：声明 × 真实数据源比对 → supported / unsupported / contradicted，防幻觉可溯源。
- `op=report`：渲染核查结果为人类可读报告。
- 复用 `solo/factory/evidence.py` 核心，加壳不改核心。

---

## 5. 交付清单

- `atoms/writing/write-qa/` + `atoms/writing/write-evidence/`（写作原子落盘）
- `registry.json`：12 原子（10 核心 + write-qa + write-evidence）
- `assemblies/fde-workflow.json`：写入写步骤（监测→诊断→写作→交付），final 含写作字段
- `tests/test_fde_linkage_deepen.py`：对齐 10 核心原子 + 写作原子（26 用例）
- 文档对齐：`_os/solo-fde-linkage-deepen.md` / `_os/solo-fde-atomic-architecture.md` 消除文档代码脱节
- pytest 全绿（264 passed）
