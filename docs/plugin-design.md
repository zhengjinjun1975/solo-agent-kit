# solo-agent-kit FDE 外部插件体系设计（v0.9 提案）

> 为 FDE 套件引入**可靠的外部插件**，增强综合能力。
> 核心：Obsidian 知识库集成 + 本机已装工具（数据/可视化/办公）+ 厂区现场能力。
> 原则：可靠优先（本机已装）、零依赖优先、外部工具 subprocess 调用。

---

## 1. 插件引入原则

| 原则 | 说明 |
|------|------|
| **可靠优先** | 优先本机已装工具（Obsidian/ssh/curl）+ 已装 Python 包，不引脆弱依赖 |
| **零依赖优先** | 能标准库实现就不下载新包 |
| **subprocess 桥接** | 外部 CLI 工具（Obsidian/ssh）用 subprocess 调用，不绑死库 |
| **可降级** | 插件不可用时不崩溃，明确报错（对齐 provider 分级） |

## 2. 本机可用资源盘点（已验证）

| 资源 | 状态 | 用途 |
|------|------|------|
| Obsidian CLI + vault | ✅ | 知识库读写/检索/归档 |
| ssh / curl | ✅ | 厂区设备远程 |
| pandas / numpy | ✅ | 高级数据分析 |
| matplotlib | ✅ | 可视化（SPC/趋势/异常） |
| openpyxl | ✅ | Excel 交付报告 |
| psutil | ✅ | 本机监控增强 |

## 3. 插件清单（按能力域）

### 3.1 知识库：Obsidian 集成（核心）
**目标**：FDE 现场产出的报告/方案/经验自动归档到 Obsidian 知识库。

> **注意**：Obsidian 笔记应用**无官方 CLI**（npm 那个 `obsidian` 是 QA 平台工具，不可用）。
> 正确方式：**直接文件系统读写 vault**（`D:/knowledge-base/obsidian-vault/`），
> 遵循 vault 目录结构（knowledge/projects/reports/daily）+ Markdown 语法（frontmatter/link/tag）。

| 能力 | 实现 | 复用现有 |
|------|------|---------|
| 现场报告归档 | 写 vault `reports/` / `projects/`（frontmatter + 正文）| memory 导出逻辑 |
| 知识检索 | 读 vault 作为决策参考 | kb-hybrid 检索 |
| 经验沉淀 | 现场经验写 `knowledge/code/atoms` | skill 逻辑 |

### 3.2 报告：数据可视化
**目标**：数据分析结果出图（SPC 控制图/趋势/异常点）。

| 能力 | 实现 | 触发 |
|------|------|------|
| SPC 控制图 | matplotlib 画 UCL/LCL/失控点 | stats.control_chart 后 |
| 趋势图 | 时间序列趋势 | stats.trend 后 |
| 异常标记 | 异常点在图上标红 | detect_anomaly 后 |

### 3.3 办公：Excel 交付报告
**目标**：分析/清洗结果生成 Excel 交付客户。

| 能力 | 实现 |
|------|------|
| 清洗报告.xlsx | openpyxl 写清洗前后对比 |
| 分析报告.xlsx | 统计指标 + 图表 |
| 本体导出.xlsx | 实体/关系表 |

### 3.4 数据：高级分析增强
**目标**：pandas/numpy 增强现有零依赖实现。

| 能力 | 实现 | 触发 |
|------|------|------|
| 大数据流式 | pandas chunk 读大 CSV | 文件 > 阈值 |
| 复杂统计 | numpy 快速计算 | 数据量大 |
| 相关矩阵 | 多列相关性 | stats.correlation 扩展 |

### 3.5 现场：设备通讯探针（厂区）
**目标**：对接厂区设备协议（Modbus/HART），采集现场数据。

| 能力 | 实现 | 依赖 |
|------|------|------|
| 设备协议探针 | 远程设备 SSH 执行 modpoll/hart | 需设备侧工具 |
| 局域网设备探测 | 纯 stdlib 扫描（ping/端口） | 零依赖 |
| 数据采集调度 | cron 定时拉设备数据 | 已支持 |

### 3.6 网络安全：设备扫描
**目标**：进厂区快速摸清局域网设备。

| 能力 | 实现 | 依赖 |
|------|------|------|
| 端口扫描 | socket 连接测试（stdlib）| 零依赖 |
| 主机存活 | ping（subprocess）| 系统 ping |
| 服务识别 | banner 抓取 | 零依赖 |

---

## 4. 插件架构设计

### 4.1 插件目录 `solo/plugins/`
```
solo/plugins/
├── obsidian.py      # Obsidian 集成
├── visualize.py     # matplotlib 可视化
├── excel_report.py  # openpyxl 报告
├── pandas_boost.py  # pandas/numpy 增强
├── netscan.py       # 局域网扫描(零依赖)
└── __init__.py      # 插件注册表
```

### 4.2 插件注册表（registry.py 扩展）
- 每个插件声明：名称/能力/依赖/是否可用
- `list_plugins()` 显示可用性（对齐 setup 检查）

### 4.3 可降级机制
- `try: import matplotlib` → 不可用则 `visualize 不可用`
- 对齐 provider 分级（EXIT_*）

---

## 5. 优先级建议

| 优先级 | 插件 | 理由 |
|--------|------|------|
| **P0** | Obsidian 集成 | 知识沉淀核心，已装 |
| **P0** | 可视化(SPC/趋势) | 数据分析直接受益，matplotlib 已装 |
| **P1** | Excel 报告 | 客户交付需要，openpyxl 已装 |
| **P1** | 局域网扫描 | 进厂区第一步，零依赖 |
| **P2** | pandas 增强 | 大数据量才需要 |
| **P2** | 设备协议探针 | 需现场设备配合 |

---

## 6. 明确不做（YAGNI）

- 不做 GUI 客户端（web 前端已够）
- 不做重型工业协议栈（Modbus 库等，用 SSH 桥接）
- 不做云同步（本地优先）

---

**待审阅**：确认插件清单与优先级是否符合你的设想。确认后我按优先级逐步实施（先 Obsidian + 可视化）。
