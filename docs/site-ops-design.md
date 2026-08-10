# solo-agent-kit 厂区运维配置与定位设计（v0.8 提案）

> 定位修正：solo 是**带着笔记本进对方厂区的 FDE 运维工具**。
> 本文档定义 site 配置层、设备台账、四项运维能力改造、定位命令，供审阅后再实施。

---

## 1. 定位修正（为什么改）

### 1.1 真实部署场景
FDE 带着这台笔记本进入客户厂区，存在**两种部署形态 + 一个服务对象**：

```
┌────────────── 笔记本(FDE带入厂区) ──────────────┐
│  solo 本机(角色=laptop)  ← 操作入口             │
│     │  SSH / 局域网                             │
│     ▼                                            │
│  ┌───────────────── 对方厂区局域网 ──────────────┐ │
│  │  服务对象(对方机器):                          │ │
│  │    现场设备 / 服务器 / MES / SCADA / PLC/网关 │ │
│  │  其中部分机器上也部署 solo(角色=on-site)      │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### 1.2 三个关键定位结论
| 维度 | 当前实现（错误） | 修正后 |
|------|----------------|--------|
| **部署** | 只当本机工具 | 支持 **laptop**(笔记本) + **on-site**(部署在对方机) 双角色 |
| **服务对象** | 监控/日志看本机 | 全部面向**对方厂区局域网设备** |
| **配置** | 只有 provider.yaml(模型) | 新增 **site 配置**：厂区上下文 + 设备台账 + 定位 |

### 1.3 核心设计原则
- **服务对象永远是对方的厂区局域网机器**（主要），solo 本机只是操作入口（次要）
- 本机监控/日志**保留但为次要**（solo 自己也要看），**设备模式为主**：前端默认展示厂区设备，本机归入"本机"伪设备
- 密码不入库（仅 host/user/port），复用现有 SSH

---

## 2. site 配置层设计

### 2.1 配置文件 `~/.solo/site.json`
```
{
  "role": "laptop",              # laptop | on-site（部署角色）
  "current_site": "华东一厂",     # 当前服务厂区（定位）
  "sites": {
    "华东一厂": {
      "location": "江苏苏州xx路",
      "contact": "王工 138xxxx",
      "devices": [
        { "name": "MES服务器", "host": "192.168.1.10", "user": "root",
          "port": 22, "group": "生产", "role": "mes" },
        { "name": "SCADA网关", "host": "192.168.1.20", "user": "admin",
          "port": 22, "group": "采集", "role": "scada" }
      ]
    },
    "华北二厂": { ... }
  }
}
```

### 2.2 字段说明
| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | str | 本机部署角色：`laptop`(笔记本)/`on-site`(部署在对方机) |
| `current_site` | str | 当前正在服务的厂区（定位锚点） |
| `sites.<name>.location/contact` | str | 厂区位置/联系人（现场上下文） |
| `devices[].name` | str | 设备名（唯一标识，运维命令用它） |
| `devices[].host/user/port` | str/int | 连接信息（**无密码**，用 SSH key） |
| `devices[].group` | str | 分组（生产/采集/测试），便于批量 |
| `devices[].role` | str | 设备角色（mes/scada/plc/server） |

### 2.3 存储实现
- 复用 `solo/base.py` 的 `atomic_write` + `lock_for`（原子写 + 并发锁）
- 新增模块 `solo/site.py`（参考 skill.py 结构，零依赖）

---

## 3. 四项运维能力改造

### 3.1 监控 monitor（现状：只看本机）
- **现状**：`system_stats()` 用 psutil 采集本机
- **改造**：新增 `monitor_device(dev_name)` —— 对台账设备远程采集
  - 远程跑 `free -m`、`df -h`、`top -bn1` 解析 CPU/内存/磁盘/负载
  - 复用 `remote.run_command()`（SSH）
  - **保留**本机 `system_stats()`（solo 自己也要看）

### 3.2 日志 logs（现状：看本机缓冲）
- **现状**：`base.py` 的 `_LOG_BUFFER`（solo 自己日志）
- **改造**：新增 `logs_device(dev_name, lines=100)` —— 远程拉设备日志
  - 远程跑 `journalctl -n 100` / `docker compose logs --tail 100` / 指定日志文件
  - 按设备归类展示
  - **保留**本机日志查看

### 3.3 远程 remote（现状：手动传 host/user）
- **现状**：`remote.py` 每个函数要手动传 host/user/port
- **改造**：新增 `remote` 层设备名解析
  - `resolve_device(dev_name)` 从 site 台账取连接信息
  - `remote_exec(name, cmd)` / `remote_deploy(name)` / `remote_logs(name)`
  - 台账设备名 → 自动填充 host/user/port

### 3.4 工单 task（现状：本机 JSON，无设备关联）
- **现状**：`new_issue(problem, severity)` 存本机，无设备字段
- **改造**：工单加 `device` 字段，关联台账设备
  - `new_issue(problem, severity, device=None)` —— device 指向台账设备名
  - `list_issues()` 带设备、按厂区过滤
  - 存本机 `~/.solo/tasks/`（单人工具，够用）

### 3.5 数据三件套对接厂区数据（清洗/分析/本体建模）

**统一原则：数据三件套与运维四大能力同一套逻辑——都对接厂区局域网机器数据。**

- **现状**：`data_connector.connect(source)` 支持 csv/sqlite/xlsx/rdbms，但数据源都是**本机路径**
- **改造**：`connect()` 扩展支持"设备数据源"，从台账设备远程取数
  - 数据来源加 `device` 字段：`{"type":"device","device":"MES服务器","remote_path":"/opt/data/mes.csv"}`
  - 实现：复用 remote SSH，远程 `scp`/`cat` 拉取数据到本机临时区，再走现有 csv/sqlite 解析
  - `clean`/`stats`/`ontology` 输入层**不改**（它们已通过 `connect` 拿数据），只需数据源支持设备

**数据三件套对接场景**：
| 能力 | 对接厂区数据 |
|------|-------------|
| **数据清洗** | 拉取 MES/SCADA 导出的原始数据 → 本机清洗 |
| **数据分析** | 拉取设备采集数据 → 本机分析（描述/趋势/SPC/异常） |
| **本体建模** | 拉取设备台账/工单数据 → 本机建厂区本体 |

---

## 4. 定位功能（新）

### 4.1 CLI 命令（新增 `solo site ...` 子命令）
| 命令 | 功能 |
|------|------|
| `solo site list` | 列出所有已配置厂区 |
| `solo site use <厂区>` | 切换到指定厂区（定位锚点） |
| `solo site devices` | 列出当前厂区的设备台账 |
| `solo site add-device <name> <host> [user] [port]` | 添加设备到当前厂区 |
| `solo site rm-device <name>` | 移除设备 |
| `solo site role` | 查看/设置部署角色（laptop/on-site） |

### 4.2 Web 前端（新增"厂区"面板）
- 顶部显示当前厂区 + 部署角色（定位一目了然）
- 设备台账 CRUD（添加/删除/分组）
- 监控/日志/远程/工单面板**默认选当前厂区**的设备

### 4.3 agent 对话路由
- 自然语言 `监控MES服务器` → `monitor_device("MES服务器")`
- `看看SCADA网关日志` → `logs_device("SCADA网关")`
- 意图识别加 site 相关的关键词

---

## 5. 实施步骤（按序，每步可验证）

| 步骤 | 内容 | 验证 |
|------|------|------|
| 1 | 新增 `solo/site.py`（site 配置 + 设备台账 CRUD + role/current_site） | 单测：add-device/use/切换 |
| 2 | CLI 加 `site` 子命令 | `solo site list` 正常 |
| 3 | `remote.py` 加 `resolve_device` + 设备名重载 | 无设备时明确报错 |
| 4 | `monitor.py` 加 `monitor_device` | 远程采集返回数据/超时处理 |
| 5 | `task.py` 加 `device` 字段 | 工单关联设备、按厂区过滤 |
| 6 | **`data_connector` 加设备数据源(device+remote_path)** | `connect({"type":"device",...})` 远程取数 |
| 7 | **clean/stats/ontology 对接设备数据源** | 远程数据能清洗/分析/本体建模 |
| 8 | Web 前端加厂区面板 + 设备选择 | 浏览器实测 |
| 9 | agent 意图加 site 路由 | 对话"监控MES服务器"路由正确 |
| 10 | 全量测试 + CodeAgent review | 43 全绿 + 新增测试 |

---

## 6. 明确不做（YAGNI）

- **不做**多用户协作（单人 FDE 工具）
- **不做**密码入库/密钥管理（用系统 SSH key）
- **不做**复杂监控指标采集（沿用 SSH 跑命令，不上 agent）
- **不做**工单中央化（存本机，FDE 现场自用）

---

## 7. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 远程采集依赖 SSH key 已配置 | `test_connection` 先测，明确报错提示配置 key |
| 厂区切换后设备失效 | `site use` 后提示当前厂区设备清单 |
| 台账密码泄漏 | 明确"密码不入库"，文档标注用 SSH key |
| 改动破坏现有功能 | 本机模式全保留，新增设备模式增量式 |

---

**待审阅**：请确认以上定位、site 配置结构、四能力改造、定位命令是否符合你的设想，确认后我按实施步骤逐步实施。
