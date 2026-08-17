---
title: solo 端到端断链全查
created: 2026-08-17
type: e2e-break-check
status: done
---

# solo 端到端断链全查（严谨全域检查 + 事件驱动 + 一企一行业一数据 + 实测到底）

## 一、一企一行业一数据场景（46/46 PASS）
华泰阀门制造厂（一企）/ 阀门制造行业（一行业）/ 阀门设备+振动+销售三张 CSV（一数据）
全链路实测到底：数据(describe/SPC/CPK) → 本体(建模10实例/问答/状态filter) → 监测(ingest 8点/MAD动态阈值upper=6.15/检出8.6异常/越限告警critical) → 诊断(知识库根因/防幻觉) → 决策(行业阈值safety=30/补货) → 写作(write-qa六维/write-evidence可溯源) → 交付(SRS/验收/勾稽/交付包/verify) → 工单状态机(open→diagnosed→resolved→verified→audit 4留痕)

## 二、事件驱动断链（15/15 PASS）
灌新数据(V011新增/V004修复/V003库存/V001新异常15.0) → 监测检出新异常、本体count 10→11、故障1→0、补货消失、交付快照含新设备
无残留旧数据、不串台（设备隔离/行业隔离：阀门safety=30 vs 化工20 决策集不同）

## 三、跨开源联动（12/12 PASS）
linkage 发现 factory/sme + codes_isolation 隔离 import + 缺失回退不崩 + 开源禁依赖闭源边界 + solo 独立可跑

## 四、发现并修复 3 处真实断链
| # | 断链 | 修复 |
|---|---|---|
| 1 | HTTP原子路由500(/api/atom /api/flow payload callable/dict) | _payload_value() 统一 |
| 2 | 本体问答残留旧数据(过滤器无匹配value=None非0条) | 0结果兜底诚实返回"共0条" |
| 3 | 组装链验收输入补全 | assemblies 补全 |

## 五、回归
```
一企场景 46/46 + 事件驱动 15/15 + 跨开源 12/12 = 73 项端到端实测全 PASS
pytest 281 passed(基线) + 组装链端到端全绿
```

## 结论
solo 端到端断链全查通过：能力链/数据流/事件驱动/跨开源无断链，一企一行业一数据全流程实测到底，修 3 处真实断链。
