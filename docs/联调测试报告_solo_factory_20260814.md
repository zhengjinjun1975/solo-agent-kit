# solo ↔ factory 开源闭源联调+测试报告（验收前）

> 日期：2026-08-14　|　执行方：CodeAgent（联调+实测）
> 范围：solo(FDE辅助) × factory开源(算法) × factory闭源(交付) 三件套数据流转闭环
> 目标：D0问题集→D1词典→D4报告 全链路可被开源/闭源消费

## 一、联调链路结论（全部实测通过 ✅）

### 1. D0 问题集：solo `draft_questions` → 闭源 `cmd_fde`/`update_examples` → 开源 `examples` → `benchmark`
- **实测**：solo 从 valve_equipment 生成 12 个问题集 → `POST /api/kbs/valve/examples` 写入开源 examples → `/api/eval/benchmark?kb=valve` 读取到新题集，`questions_n` 从 5 → 12，命中率 1.0（12/12 全命中）。
- **消费链完整**：`client.update_examples(kb, questions)`（REST）→ 开源 `kbs_update_examples` 端点 → 全局 KBS 缓存刷新 → benchmark 读取新 examples。措辞已对齐引擎极值模板（`功率最大的设备`），规则引擎可答。
- 测试后已恢复原 examples（`有多少台设备/功率最大的设备/设备类型有哪些/不锈钢材质的设备/客户总数`）。

### 2. D1 词典：solo `lexicon_draft` → `to_factory_lexicon`（开源）/ `to_review_items`（闭源 review）
- **开源消费**：`to_factory_lexicon(draft, table_name, entity_cn)` 输出顶层键 `attr_cn2en/attr_en2cn/type_cn2en/status_cn2en/zone_cn2en/entity_cn2en/numeric_fields/field_aliases/value_fields/description`，与引擎 `lexicon_*.json` 契约键完全对齐（实测对照 lexicon_ai4i.json 键集一致）。
- **闭源 review 消费**：`to_review_items(draft)` 转成 `[(item_type,key,value),...]` → `start.py ingest-lexicon 阀门制造 <draft.json>` 逐条 `review.add(..., suggested_by="solo")` 写入 review 队列。实测写入 20 条（type_enum/attr_mapping/status_enum），raw dict 结构亦可被 solo 转换器降级处理。
- 测试残留已清理（DELETE suggested_by='solo'）。

### 3. D4 报告：solo `report_draft_dict` → 闭源 `deliver.report`
- **对齐**：solo `report_draft_dict` 字段（`kb/industry/generated_at/命中率{baseline,current,提升}/资产版本数/自进化健康度/说明/solo_draft`）与闭源 `deliver.report()` 核心字段完全重合（命中率/资产版本数/自进化健康度/kb/industry/generated_at），solo 草稿可被闭源识别（`solo_draft:True`）并补全 `资产版本链/人在环审查/遗留问题`。
- **实测**：`start.py deliver 阀门制造` 正常出报告（命中率 0→1.0，人在环审查 126 待确认）。

## 二、测试执行结果

| 仓 | 测试 | 结果 |
|:--|:--|:--|
| solo-agent-kit | pytest | 43 passed ✅ |
| factory-ontology-kit | pytest | 35 passed ✅ |
| factory-ontology-kit | e2e_test.py | 17/17 ✅ |
| ontology-delivery-tool | pytest | 33 passed ✅ |
| 闭源 REST 边界 | AST 全量扫描 | ✅ 零开源 import（仅 stdlib + 内部模块 + psutil + solo）|

## 三、问题清单

### P0（必修，验收阻塞）
**无**。三条联调链路 D0/D1/D4 全部实测跑通，无断链。

### P1（建议修，验收前） 
1. **双注册表不同步（已知，实测复现）**：闭源 registry 标 `已接入` 的 `能源站(energy_station)`/`通用制造(manufacturing)`/`五金加工(hardware)` 在开源 kbs.json **缺失**。`check_registry_sync()` 已告警但只是静态提示，不会自动补 kbs 条目。→ 这 3 个行业 `ask`/`benchmark` 会落到错误 kb 或报"无评测题"。**必修**（至少 list 时明确告警并引导 `setup <行业> <csv>` 建模补 kbs）。
2. **solo 集成函数无单元测试（P1 回归风险）**：`draft_questions/lexicon_draft/to_factory_lexicon/to_review_items/report_draft_dict` 是 solo↔factory 契约的核心，但 `tests/` 无任何直接调用它们的用例（test_core/test_e2e 未覆盖）。联调全靠手工，一旦改动无回归保护。→ 补契约函数单测（至少 to_factory_lexicon 键集 + to_review_items 结构 + draft_questions 措辞断言）。

### P2（优化项）
1. **`to_review_items` 未过滤 id/编号列**：`to_factory_lexicon` 已过滤 id 列，但 `to_review_items` 仍把 `id` 列产出 `('attr_mapping','id','id')` 污染 review 队列（实测产生，已清理）。→ 统一过滤逻辑。

## 四、修复建议（P1）
1. 双注册表：`check_registry_sync` 告警基础上，`cmd_fde` D0 阶段对缺失 kb 的行业直接触发 `setup`（或明确提示，避免交付到错误 kb）。
2. solo 契约单测：在 `tests/` 新增 `test_factory_contract.py`，覆盖 to_factory_lexicon 键对齐 / to_review_items 过滤 id / draft_questions 措辞对齐引擎模板。

## 五、总结
三件套数据流转闭环（D0问题集→D1词典→D4报告）已**真实执行端到端跑通**，无 P0。遗留 P1 两项（双注册表同步 + solo 契约函数缺单测），建议验收前修复。
