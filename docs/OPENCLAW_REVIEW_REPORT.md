# solo-agent-kit v0.5.0 工程审查报告

> 审查人：OpenClaw ｜ 2026-08-10 ｜ 环境：Python 3.11.15 / pytest 9.1.1 / Ollama 在线（ornith + nomic-embed）/ DeepSeek key 未设（降级路径已测）
> 全部实测，非纸面审查。完整报告已存档：`workspace\solo-agent-kit-v0.5.0-review-20260810.md`

---

## 〇、总评

**结论：通过（有条件）。** 18 项单测全过、14 项 CLI 全过、36 项 Web API 全过；零依赖属实（核心 2121 行 < 4000 行红线）；双套件边界清晰；"本体优先"差异化成立。但审查实测抓到 **3 个真 bug + 1 个功能缺陷 + 4 项安全点**，以及 3 处"蓝图承诺未兑现"（task 无入口、skill 意图空转、模型分层未到 agent 层）。

一句话：**测试绿灯，代码有真 bug，设计方向全对，方法论落地七成，反过度工程守住了。**

---

## 一、完整测试结果

### 1.1 pytest（18/18 通过，2.20s）

| 模块 | 用例 | 结果 |
|------|------|------|
| 版本 | test_version | ✅ |
| 记忆 | profile覆盖 / 事实去重 / 场景+检索 / Obsidian互通 | ✅ ×4 |
| 本体 | 单表 / 工厂关系导航 / 多表跨实体 | ✅ ×3 |
| skill / writing | 触发匹配 / D5 AI味检测 | ✅ ×2 |
| code | impact / overview+explain | ✅ ×2 |
| gen / clean / stats / task | 签名 / 清洗三件套 / 统计+SPC / 状态机 | ✅ ×4 |
| provider | 无key→EXIT_AUTH(3) / 本地挂→EXIT_NETWORK(2) | ✅ ×2 |

**缺口**：agent / web_server / cli 无单测（本次实测已补）；gen 只测签名；code 只测顶层符号（未暴露下述 P0-2）。

### 1.2 端到端 CLI（隔离 USERPROFILE，不污染真实数据）

| 命令 | 结果 | 要点 |
|------|------|------|
| version / init | ✅ | 0.5.0；mem_dir 正确隔离 |
| setup | ✅ | python✓ ollama✓(ornith+nomic) config✗(无yaml) memory✓ |
| config（未配置/已配置） | ✅ | 脱敏显示 api_key_env ✓ |
| skill-add | ⚠️ | `{"added":true}`——**写进记忆事实层而非 skill 索引**（P1-6） |
| import-obsidian / export-markdown | ✅ | 2 条导入；solo-memory.md 导出 |
| run --tier local | ✅ | 循环五态走通，**记忆注入生效**（回答含 skill 内容） |
| run --tier remote（无key） | ⚠️ | **被意图路由截胡**："分析本体建模…"→stats，未达 remote（P1-7） |
| factory-clean / stats / onto | ✅ | 24→21 行；58.9 异常检出+SPC✓；3 实体 56 triples✓ |
| 未知命令 | ⚠️ | rc=2，与 EXIT_NETWORK=2 **语义撞车**（P0-5） |

### 1.3 Web 后端（36/36 通过，起服务实测）

| 类别 | 结果 |
|------|------|
| capabilities / config / memory / skills / setup / stats / memory-search / code-overview | ✅ 全 200（stats 缺参→400 ✓） |
| /api/agent 意图路由：clean·stats·ontology·memory_search·writing·code_overview·gen·setup | ✅ 8/8 路由正确 |
| /api/agent：skill | ⚠️ **意图声明未实现，掉 chat**（P1-6） |
| /api/agent：chat 兜底 | ⚠️ **自称 Ornith——身份幻觉**（P0-3） |
| writing / gen / clean / ontology / memory-add / skill-add / toggle / config写 | ✅ 全 200 |
| 未知 API / 静态文件 / 404 | ✅ |
| **路径穿越 5 连测**（裸../、%2e%2e、深层、%2f混合、同前缀） | ✅ 全 404，**防御实测有效** |

---

## 二、代码审查报告（分级）

### P0 · 必须改（实测复现）

| # | 位置 | 问题 | 证据 | 修复 |
|---|------|------|------|------|
| P0-1 | `stats.detect_anomaly()` | **空数据 iqr → IndexError 崩溃** | 实测 `detect_anomaly([], "iqr")` 崩 | `len(vals)<4 → return []` |
| P0-2 | `code.py RE_DEF` | **只索引顶层符号：39/161（24%）**，方法/嵌套类全丢 → 影响分析在真实项目实质失效 | 实测 `add_fact in symbols = False`；E2E 的 code-overview 符号数 39 印证 | 正则加 `\s*` 支持缩进 |
| P0-3 | `agent.py` chat 兜底 | **无身份锚定 → 模型自报错误身份** | 实测"你好"→"我是 **Ornith**…" | prompt 加 system 角色 |
| P0-4 | `web_server.py` | **CORS `*` + 无鉴权 + 任意路径参数**（csv/dir/relations 可读任意路径；/api/config 可改写 provider.yaml） | 实测端点可传任意路径 | CORS 收窄/移除；路径参数白名单；config 写加确认 |
| P0-5 | `cli.py` | **argparse 退出码 2 与 EXIT_NETWORK=2 撞车**（应属 EXIT_USER_ERR=1） | 实测 `solo nosuchcmd` rc=2 | main() 捕获 SystemExit 转译 |

### P1 · 建议改

| # | 位置 | 问题 |
|---|------|------|
| P1-6 | agent/cli | **skill 两处空转**：INTENTS 声明了但 run() 无分支；CLI skill-add 调 `add_fact` 写错层 |
| P1-7 | agent.route() | 关键词无优先级：实测"分析本体建模"→stats 抢走；"设备/工单"过宽；gen 词表有重复项 |
| P1-8 | stats.trend() | 非数值过滤后 **x 轴错位 → 方向误判**（实测上升序列被判 flat） |
| P1-9 | agent/gen | **模型分层未到 agent 层**：gen 固定 local，9B 模型写 README 输出"我先了解一下项目结构…" |
| P1-10 | agent→web_server | **反向依赖** + `_setup_checks` 双实现，应抽 `solo/setup.py` |
| P1-11 | _serve_static | startswith 前缀校验有理论漏洞（`web_evil` 同前缀），改 commonpath |
| P1-12 | task.py | **类完整但零入口**——VISION §17/§23 承诺空转，predict 无人调用 |
| P1-13 | web_server | `/api/run` 与 `/api/agent` 重复；`/api/toggle` 只改内存布尔不生效 |
| P1-14/15 | 全库/clean | `_load` 损坏静默（下次写入覆盖丢数据）；guess_type 只取首行猜整列 |

### 可接受（反过度工程，明确不改）

| 项 | 判定 |
|----|------|
| clean(24)/code.index(20)/scan(14) 圈复杂度 | **不拆**——单文件可审计、测试覆盖核心路径，拆分反增跳转成本 |
| `from __future__ import annotations` 误报 | **确认误报**，延迟注解惯例 |
| bigram 语义检索 | v1 接受（短记忆条目够用，零依赖优先） |
| `_refs()` 全量重扫 / `_find` 子串匹配 | 接受，轻量项目代价可忽略 |
| writing 规则稀疏（7 错字/5 语病/6 AI 词） | v1 接受但**名不副实**（宣称"复刻 zh_writing_checker"对方数百规则）——补规则或改宣称 |

---

## 三、设计审查结论

| 问题 | 结论 |
|------|------|
| **双套件分离** | ✅ **合理**。factory/=数据域，solo/=能力域，依赖方向干净（agent 是唯一编排层）。唯一问题：agent 反向依赖 web_server（P1-10） |
| **意图路由** | ⚠️ **方向对，精度不足**。8 意图覆盖主要能力，但缺 task/export/import/config 意图 + skill 空转 + 无优先级。**LLM 意图 v2：拒绝现在升**——规则增强（优先级+互斥+否定词）可零成本解决 90% 误路由，LLM 意图等 gateway 化再评估 |
| **provider 分层** | ✅ **符合"轻≠不行"**。无 key 明确报错不静默降级✓；远端挂→本地✓。但**分层只兑现到 provider 层，agent 层全走 local**（P1-9） |
| **前端** | ✅ **合格**。浅色 `#f4f6fa`+蓝橙点缀，护眼且适合工程长时间使用；XSS 转义到位；对话中心+快捷指令+能力面板成立。缺：SPC/趋势图（P2 加内联 SVG，零依赖） |

---

## 四、方法论缺口清单

**已落地 ✅**：零依赖（2121 行）、本体优先、三层两域、skill 浅层、六维检查、CodeGraph（顶层）、provider 分层、Obsidian 互通、分级退出码（provider 层）、双套件+Web+CI、JSON in/out。

**未落地 —— 判定**：

| 项 | 判定 |
|----|------|
| task.py 用户入口 | **该补（P1）**——类写好了没入口，且是 AHE 决策可观察性的最小种子 |
| agent 层模型分层 | **该补（P1）**——"复杂→远端"承诺未兑现 |
| 可证伪预期闭环（predict 自动记录） | **该补（P1 种子版）** |
| **记忆语义检索 sqlite-vec** | **暂不换（P2 观察）**——bigram 对短记忆实测够用；C 扩展破坏"纯标准库"卖点；触发条件：记忆 >2000 条。但 `semantic=True` 名不副实，可加"nomic 可用时真嵌入、否则 bigram"的可选升级 |
| **harness 自进化（AHE）** | **v1.5 不做，v2 启动**——核心方法论未立稳，自进化是沙上盖楼；VISION §23 自己承诺"v1 只预留不实现"，守承诺。先落 predict 种子 + 修 P0-2（符号索引是组件可观察性的地基） |
| ACON 压缩 / 插件 / YAML 工作流 / 主动思考 / 多源导入 / 身份审计 / MCP | 全部 **P2 或 gateway v2 暂缓** |

**该砍（过度设计）**：AHE 完整闭环（v2）、LLM 意图（v1.5 规则替代）、`/api/toggle`（装饰性 API）、`/api/run`（重复端点）、前端框架化、多 agent/团队/权限（守 §6 边界）。

---

## 五、优化方案

**P0（本次迭代）**：① detect_anomaly 空数据防护 ② CodeGraph 支持缩进符号+补方法级测试 ③ chat 兜底身份锚定 ④ web_server CORS 收窄+路径参数白名单+config 写确认 ⑤ CLI 退出码转译

**P1（下个迭代）**：⑥ skill 意图实现/移除 + CLI skill-add 改调 Skill.add ⑦ 意图路由增强（优先级+互斥+否定词+宽词收窄）⑧ trend() 索引修复 ⑨ agent 层模型分层落地 ⑩ task 接入（CLI+意图+自动 predict）⑪ _setup_checks 抽独立模块、合并 /api/run ⑫ commonpath 校验+静默失败告警 ⑬ guess_type 全列投票

**P2（权衡）**：前端 SVG 图表、sqlite-vec/真嵌入评估（>2000 条触发）、writing 规则扩充或改宣称、记忆容量上限、多源导入、访问日志。

**明确不做**：AHE 自进化（v2）、LLM 意图（v1.5 规则替代）、sqlite-vec 现在换、YAML 工作流/插件/MCP（gateway v2）、前端框架化、多 agent/团队/权限。

---

## 六、给技术负责人的三句话

1. **测试绿灯，可以继续迭代**——但 P0 五项必须下个版本前修掉：崩溃、符号索引、身份幻觉、安全、退出码，它们会直接砸"轻≠不行"的招牌。
2. **设计方向全部正确**——真问题在"兑现层"：蓝图写了、类写了，但 agent 路由、task 入口、模型分层没接上。
3. **四个"拒绝"我全部支持**（圈复杂度不拆、LLM 意图不升、AHE 不启动、sqlite-vec 不换），且都给了触发条件，防止将来拍脑袋引入。

*审查脚本已清理，仓库工作区无残留（仅剩委托消息 docs/OPENCLAW_TASK_MSG.md 未跟踪，属正常）。*