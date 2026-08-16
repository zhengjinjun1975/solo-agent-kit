# FDE 最新技术深度检索（代表最新 2024-2026 · 最细可落地 · 为迭代准备）

> 项目：`solo-agent-kit`（FDE 甲方乙方工程师共用工具）
> 用途：**避免优化浅化**——把 FDE 综合能力对标 2024-2026 最新技术栈，逐项给"最新技术 + 最细落地描述（依赖/参数/流程/数据格式/API）+ 差距 + P0-P2 优化方案"。
> 现状基线：`solo/factory/monitor.py`（JSON 时序 MetricStore + 阈值/突变告警 + 工单状态机）、`protocols.py`（TCP/HTTP/MQTT/Modbus/OPC-UA 适配器）、`MonitorAsk`（关键词路由问数）、`Ontology`（CSV→本体→问答）、`Memory`（三层两域）、`assist.py`（问题集/词典/报告起草）。
> 版本锚点：本文件所列库版本经 **PyPI JSON API 实测核验（2026 年中）**；模型/规范/产品名基于最新生态知识。落地前请复验一次版本号。

---

## 0. 一句话结论（供决策）

solo FDE 目前的监测是"**零依赖规则引擎 + JSON 文件时序 + 关键词问答**"，在**存储、算法、协议、知识、智能体**五层都停留在 2024 年前水平。对标 2024-2026 最新最佳实践，差距集中为 6 点：① 无真实时序库与高吞吐采集；② 无 ML 级异常检测（只有阈值+环比）；③ 无边缘 AI 推理与量化/蒸馏闭环；④ 协议未吃透 MQTT5/SparkplugB/OPC-UA PubSub；⑤ 无离线 RAG/小模型知识库（本体问答非语义检索）；⑥ 无现场 Agent/多模态/语音。P0 应在"**真实时序 + 混合异常检测 + 离线 RAG + MQTT5/OPC-UA 直采 + 工具调用 Agent + 语音 I/O**"上补齐，全用 ONNX/轻量小模型，可完全离线交付。

---

## 一、最新技术检索（2024-2026，逐项给框架/模型/协议/方法+版本细节）

### 1.1 设备监测 · 边缘 AI / 轻量模型 / 小模型

| 技术方向 | 最新代表（2024-2026） | 关键版本/细节 |
|:--|:--|:--|
| 端侧推理运行时 | **ONNX Runtime** | 实测 `onnxruntime 1.28.0`。Execution Provider：CPU/XNNPACK、CUDA、TensorRT、**OpenVINO**、DirectML、CoreML、WebGPU。量化用 `onnxruntime.quantization`（QOperator/QDQ 动态/静态/权重+激活 int8）。 |
| 端侧 LLM 推理 | **ONNX Runtime GenAI** / ExecuTorch / llama.cpp | `onnxruntime-genai 0.15.2`；`llama-cpp-python 0.3.34`（GGUF + GPTQ/AWQ 量化）；PyTorch **ExecuTorch**（替代 PyTorch Mobile，XNNPACK/Qualcomm QNN/CoreML，支持 4bit QAT LLM）。 |
| Intel 加速 | **OpenVINO** + NNCF | 实测 `openvino 2026.3.0`。NNCF 做 PTQ/感知量化；OpenVINO GenAI 做端侧 LLM。 |
| 嵌入式/MCU | **TFLite Micro** / Edge Impulse / NanoEdge AI / STM32Cube.AI | Edge Impulse 经典 ML AutoML；NanoEdge AI Studio（异常检测 AutoML）；STM32Cube.AI 神经转换。 |
| 边缘算力平台 | **NVIDIA Jetson Orin** | JetPack 6.x；Orin Nano Super（2024-12，fp16 ~67 TOPS，$249）；TensorRT 10.x + TAO Toolkit。 |
| 通用嵌入/分类小模型 | **PyOD / scikit-learn / LightGBM** | 实测 `pyod 3.6.4`（30+ 异常检测算法）、`scikit-learn 1.9.0`、`lightgbm 4.7.0`、`xgboost 3.4.1`。 |
| 在线增量学习 | **River** | 实测 `river 0.25.0`——流式/在线 ML，增量异常检测与漂移检测。 |

### 1.2 小模型 / 知识蒸馏（2024-2026）

| 方向 | 最新代表 | 细节 |
|:--|:--|:--|
| 蒸馏经典方法 | DIST / DKD / DMT | **DIST**（解耦蒸馏，CVPR'22）——分类分 logit 与 feature 蒸馏；**DKD**（解耦知识蒸馏）把 KD 拆为 target/non-target；**DMT**（分布匹配蒸馏）。 |
| LLM 蒸馏 | MiniLLM / reverse-KL / 合成数据蒸馏 | 用大模型**合成/标注数据**再小模型续训（Phi/Qwen-turbo 路线）；reverse-KL 避免 mode collapse；渐进式蒸馏。 |
| 时序模型蒸馏 | 把 foundation TS 模型蒸到 TTM | 用 TimesFM/Chronos 作为 teacher，蒸馏到 **TinyTimeMixers（TTM，1-5M 参数）**。 |
| 蒸馏工具链 | torchao / QAT / ONNX QDQ | 量化感知训练（QAT）+ int8/int4；`onnxruntime.quantization` 静态 QDQ。 |

### 1.3 时序异常检测 / 预测（2024-2026 最新方法）

| 类别 | 最新代表 | 细节 |
|:--|:--|:--|
| 时序 foundation 模型 | **TimesFM 2.0**（Google）/ Chronos / Moirai / TTM / Lag-Llama | TimesFM：patch-based decoder-only，200M 参数，零样本预测；TimesFM 2.0（2025）增强零样本与新域泛化。Chronos（Amazon，T5 架构）。Moirai（Salesforce 通用时序模型）。**TTM**：轻量可蒸馏。 |
| Transformer 预测 | **PatchTST** / **iTransformer** | PatchTST（patch 分块 + 通道独立，ICLR'23）；iTransformer（ICLR'24，倒置 transformer 统一多变量）。 |
| 异常检测算法 | **Anomaly-Transformer** / TimesNet / **DIF** / KiloGram / NSP | Anomaly-Transformer：关联差异注意力；TimesNet：多周期发现；**DIF（Deep Isolation Forest, 2024）**；KiloGram（长时序异常,2024）；NSP（NeurIPS'23）。 |
| 工程库 | **PyOD / River / sktime / anomalib** | 实测 `pyod 3.6.4`、`river 0.25.0`、`sktime 1.1.0`、**`anomalib 2.6.0`**（异常检测工业套件，多模型+可视化）。 |
| 流式/在线 | Streaming MAD / S-ESD / adaptive threshold | 稳健统计：中位数绝对偏差（MAD）、Twitter ESD（季节性 ESD）、自适应高斯阈值、River 流式隔离森林。 |
| 边缘异常检测 | NanoEdge AI / 轻量自编码器 | MCU 级异常检测 AutoML；单变量轻量自编码器量化到 ONNX。 |

### 1.4 OPC-UA / MQTT 5 最新

| 方向 | 最新代表 | 细节 |
|:--|:--|:--|
| OPC-UA 规范 | **UA 1.05.03**（2024）+ PubSub（Part 14） | 传输：UADP / JSON / XML；**PubSub over MQTT**（默认 MQTT 3.1.1 亦可 MQTT5）；UA-TSN；配套规范：**OPC UA for Machinery（MDIS）、DI、Robotics、PA-DIM**。 |
| Python 客户端 | **asyncua 2.0.1**（实测） | 异步；客户端/服务器/订阅/方法调用；支持安全（SignAndEncrypt, Basic256Sha256）、证书 X.509。 |
| C 客户端 | **open62541** | 1.3.x；嵌入式友好；PubSub 支持。 |
| MQTT 5 | **MQTT 5.0（OASIS）** | 新特性：Reason Code、**User Properties**、**Message Expiry**、**Topic Alias**、**Request/Response（Correlation Data）**、会话过期、流控、Shared Subscription。 |
| Sparkplug B | **Eclipse Tahu**（Sparkplug 3.0.x） | 定义 state/DBIRTH/DEATH 命名空间与生命周期；topic：`spBv1.0/<group_id>/<message_type>/<edge_node_id>/<device_id>`；5 种消息：NBIRTH/NDEATH/DBIRTH/DDEATH/DATA；支持 MQTT5。 |
| Python MQTT | **paho-mqtt 2.1.0**（实测） | 原生 MQTT5 支持（`mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)`，`mqttv5`）。 |
| Broker | **EMQX 5.x** / HiveMQ / NanoMQ / Mosquitto 2.x | EMQX 5：完整 MQTT5、内置规则引擎/数据桥接、百万连接；HiveMQ 企业级；Mosquitto 轻量。 |

### 1.5 现场诊断 · AR / 数字孪生 / PHM

| 方向 | 最新代表 | 细节 |
|:--|:--|:--|
| AR | **Apple Vision Pro / ARKit 6 / ARCore / WebXR / Vuforia** | visionOS + RealityKit；**WebXR Device API**（Three.js / model-viewer）免装 App；**OpenXR 1.1**（跨厂商）；Vuforia Engine 10/11（工业 marker/模型跟踪）。 |
| 数字孪生 | **NVIDIA Omniverse** / Unity 6 / Unreal 5 / Siemens Xcelerator | Omniverse 用 **OpenUSD + Kit SDK + RTX** 做实时工厂数字孪生；Unity 6（2024）Runtime；**Cesium + 3D Tiles** 流式大场景；**glTF 2.0** 轻量 3D 交换。 |
| PHM/预测性维护 | **RUL 预测 / 健康指数 HI / C-MAPSS** | 剩余寿命回归（LSTM/CNN-LSTM/Transformer on C-MAPSS）；健康指数曲线拟合；Weibull/Cox 生存分析；物理信息 ML + 贝叶斯标定。商用：GE APM、IBM Maximo、PTC ThingWorx、Seeq、Augury。 |

### 1.6 交付/知识 · 离线 RAG / 小模型知识库 / 移动端 / 低代码现场工具

| 方向 | 最新代表 | 细节 |
|:--|:--|:--|
| 离线 LLM 推理 | **llama.cpp / Ollama / llama-cpp-python** | GGUF 量化（Q4_K_M 等）；`llama-cpp-python 0.3.34`；`onnxruntime-genai 0.15.2`；完全离线。 |
| 小模型知识库 | **Qwen2.5 / Qwen3 / Phi-4-mini / Gemma 3 / Llama 3.2** | Qwen2.5-0.5B/1.5B/3B（2024-09）；**Qwen3-0.6B~（2025-04，hybrid 思考 + 原生工具调用）**；Phi-4-mini 3.8B（2025-02）；Gemma 3-1B/4B；Llama 3.2-1B/3B（on-device）。 |
| 向量库 | **Chroma / LanceDB / Qdrant / sqlite-vec / FAISS** | 实测 `chromadb 1.5.9`、**`lancedb 0.37.1`**（嵌入式、边缘友好）、`qdrant-client 1.19.0`、`sqlite-vec 0.1.9`。 |
| 嵌入模型 | **bge-m3 / Qwen3-Embedding / E5 / gte** | bge-m3（BAAI，1024 维，dense+sparse+multi-vector，多语，8192 上下文）；**Qwen3-Embedding-0.6B/4B/8B（2025）**；bge-reranker-v2-m3 重排。 |
| RAG 高级方法 | **混合检索 + Rerank / GraphRAG / Contextual Retrieval / Agentic RAG** | BM25+向量混合；Rerank 二阶段；微软 **GraphRAG**（2024）做知识图谱增强；Anthropic **Contextual Retrieval**（2024-09）；父子块、agentic 多跳检索。 |
| 移动端 | **Core ML / ML Kit / ONNX Runtime Mobile / Flutter / RN** | 端上小模型推理；MediaPipe；React Native/Flutter 跨端。 |
| 低代码现场工具 | **Node-RED / ThingsBoard / Grafana / Appsmith / ToolJet** | Node-RED 流编排（MQTT/OPC-UA 节点）；**ThingsBoard** 规则引擎+仪表盘+边缘；Grafana 可视化；Appsmith/ToolJet 内部工具。 |

### 1.7 Agent / 现场 Agent / 多模态 / 语音

| 方向 | 最新代表 | 细节 |
|:--|:--|:--|
| Agent 编排 | **LangGraph / AutoGen→AG2 / CrewAI / OpenAI Agents SDK / Google ADK / smolagents** | LangGraph：图式状态机+断点+人机确认；AG2（AutoGen 0.4 重写）；OpenAI Agents SDK（2025）；Google **ADK**（2025）；HF smolagents（CodeAct）。 |
| 工具协议 | **MCP（Model Context Protocol）** | Anthropic 2024-11 开源；spec v2025-03-26/v2025-06-18；传输 **stdio / streamable HTTP**；暴露 tools/resources/prompts；工具可插拔。 |
| 工具调用 | 原生 function calling / structured output | Qwen3/Llama 3.1+/GPT-4o 原生工具调用；JSON schema 结构化输出。 |
| 多模态视觉 | **Qwen2-VL / Qwen2.5-VL / Qwen3-VL / Gemma 3 / InternVL** | 视觉语言模型；Qwen2.5-VL（2025-01）；Gemma 3 原生多模态；可用于现场拍照诊断、OCR 铭牌、仪表识别。 |
| 语音 ASR | **Whisper / faster-whisper / sherpa-onnx / Parakeet / Moonshine / Vosk** | 实测 `faster-whisper 1.2.1`（CTranslate2，快 4x）、**`sherpa-onnx 1.13.5`**（离线 ASR+VAD，onnxruntime 驱动，中文 Paraformer/Zipformer 模型）、Moonshine（2024 端上小 ASR）。 |
| 语音 TTS | **CosyVoice / Edge-TTS / MeloTTS / Piper / Kokoro / Zonos / ChatTTS** | CosyVoice（阿里，2024，零样本克隆）；Piper 端上极快；ChatTTS 中文；Edge-TTS 免费。 |
| 语音 Agent 框架 | **Pipecat / LiveKit Agents / OpenAI Realtime** | Pipecat（Daily 开源框架，编排实时语音 Agent）；VAD 用 Silero VAD（onnx）；流式 ASR+TTS。 |

---

## 二、最细可落地描述（每个优化点：实现方式/依赖/参数/流程/数据格式/API）

> 约定：代码为 Python；离线优先；ONNX 为统一推理格式；所有"待迭代"均给出可直接落地的细节。

### 2.1 真实时序存储与高吞吐采集（替代 JSON 文件）

- **实现**：在 `MetricStore` 底层引入嵌入式/列式时序库，保留现有 `device_metric` 语义。
  - 选项 A（推荐离线/单机）：**LanceDB**（`lancedb 0.37.1`）或 **sqlite-vec**（`sqlite-vec 0.1.9`）+ 预聚合表。
  - 选项 B（高频采集）：**Redis Stream** 做缓冲 + 落盘；**InfluxDB/QuestDB** 做列式时序（更强但依赖较重）。
- **依赖**：`pip install lancedb sqlite-vec`（LanceDB 自带磁盘列式格式，无需服务端）。
- **参数**：采集批 `batch_size=1000`；预聚合窗口 `aggregate_minutes=1`；保留策略 `retention_days=90`；写入 `parquet` 压缩（LanceDB 默认）。
- **流程**：`Source.collect()` → 统一数据点列表 → `MetricStore.ingest_batch(points)`（一次写批）→ 按分钟桶 `aggregate()` 生成 `device_metric_1m` 表 → 供查询与告警。
- **数据格式**（保持现有，扩展 tags）：
  ```json
  {"device_id":"pump_01","metric":"vibration","value":2.31,"ts":"2026-08-16T10:00:00+08:00","tags":{"unit":"mm/s","line":"A"}}
  ```
- **API**：
  ```python
  store.ingest_batch(points)                     # 批量写
  store.range(device_id, metric, start, end)     # 区间查询（新增，比 window 更细）
  store.aggregate(device_id, metric, "1m", ["mean","min","max","count"])
  ```
- **效益**：从 O(全部 JSON 重读) 到列式随机读，支撑 10³~10⁶ 点/秒采集与分钟级长窗口分析，是后续 ML 的基础。

### 2.2 ML 级时序异常检测（替代纯阈值+环比突变）

在 `AlertEngine` 之上新增 `AnomalyDetector`，两层：
- **层1 统计（零依赖，先上线）**：窗口稳健基线（MAD 代替中位数）、季节性（周/日周期）、自适应阈值（均值±k·std，k 可配）。
- **层2 轻量 ML（ONNX，离线）**：
  - 模型：单变量 **轻量自编码器 / Isolation Forest / 季节性-ESD**；多变量 **iTransformer / TimesNet** 蒸馏后的小模型；用 **PyOD**（`pyod 3.6.4`）训练，导出 ONNX。
  - 依赖：`pip install pyod onnxruntime`；如需训练 `torch 2.13.0` + `anomalib 2.6.0`。
  - 参数：`lookback=168`（一周小时点）、`latent_dim=8`、`recon_threshold_p95`、`batch_size=64`、`eps=1e-6`。
  - 流程：`window(device, metric, 168h)` → 归一化（保存 mean/std）→ ONNX 推理 → 重建误差 → 超阈值告警（复用现有 alert→ticket 闭环，`type="ml_anomaly"`）。
- **数据格式**：告警记录增加 `{"type":"ml_anomaly","score":0.93,"baseline_mean":..,"threshold":..}`。
- **API**：
  ```python
  det = AnomalyDetector(model_path="models/pump_vib.onnx", window=168)
  score = det.score(window_points)   # 返回异常分
  det.ingest_live(points)            # 流式更新基线
  ```
- **效益**：从"固定阈值漏报/误报"到"自适应、多变量、周期性感知"，大幅降低 FDE 现场误告警与漏告警，是 P0 性价比最高点。

### 2.3 边缘 AI 推理与量化/蒸馏闭环

- **推理**：统一 ONNX 格式；`onnxruntime 1.28.0` CPU/OpenVINO provider；边缘设备可用 Jetson（TensorRT provider）。
- **量化**：`onnxruntime.quantization.quantize_static(model, calibration_data, PerChannel=True, weight_type=QuantType.QInt8)`；`quantize_dynamic` 快速通道；评估 WER/准确率退化。
- **蒸馏流程**（P2，LLM/大模型→小模型）：
  1. 用大模型（如 Qwen3-70B）对设备运维语料**合成 QA/标签**（`transformers 5.15.0` + vLLM）。
  2. 小模型（Qwen3-0.6B/1.5B）在合成数据上 LoRA/全参续训（PEFT）。
  3. 用 **reverse-KL / DIST / DKD** 目标：`loss = CE(student,label) + λ·KL(teacher_logits||student_logits)`。
  4. 导出 ONNX/GGUF，QAT int8/int4，端侧部署。
- **依赖**：`transformers 5.15.0`、`peft`、`bitsandbytes`、`onnxruntime-genai 0.15.2`。
- **数据格式**：蒸馏数据 `{input, teacher_output, student_label}` JSONL；评估用准确率/困惑度。
- **效益**：把云端大模型能力压缩到可离线交付的 0.5-3B 小模型，是"现场离线可用"的关键使能。

### 2.4 OPC-UA / MQTT5 / Sparkplug B 直采升级

- **OPC-UA**：从 `opcua` 迁移到 **`asyncua 2.0.1`**（异步、现代）；新增 `OpcuaPubSubSource` 订阅（Part 14 PubSub over MQTT）；补安全：X.509 证书、`SignAndEncrypt / Basic256Sha256`；支持 **OPC UA for Machinery** 信息模型读取设备诊断节点。
- **MQTT5**：升级到 **`paho-mqtt 2.1.0`**（`CallbackAPIVersion.VERSION2` + `mqttv5`）；启用 **User Properties**（携带现场/租户/批次元数据）、**Message Expiry**（过期告警不积压）、**Topic Alias**（省带宽）、**Request/Response**（命令下发）、**Shared Subscription**（多实例负载）。
- **Sparkplug B**：新增 `SparkplugSource`（用 paho-mqtt 订阅 `spBv1.0/<group>/<DATA|DBIRTH|DEATH>/<edge>/<device>`），解析 NBIRTH/DBIRTH/NDEATH/DDEATH/DATA，**自动登记设备上线/离线**，映射到统一 `device_metric`。
- **依赖**：`pip install asyncua paho-mqtt`（opcua 若已装可保留兼容）。
- **流程**：设备(Gateway) → EMQX（Sparkplug B/MQTT5）→ `SparkplugSource`/`MqttSource` 订阅 → 解析 → `MetricStore.ingest` → `AlertEngine`。
- **数据格式**：Sparkplug 指标名（如 `spBv1.0/factory/DATA/edge01/pump1` 内 `[{"name":"vibration","value":2.31}]`）映射为 `device_id=pump1, metric=vibration`。
- **效益**：打通工业现场标准协议，拿到"设备生命周期/上线离线/诊断状态"，FDE 才能真正接真实产线而非 Mock。

### 2.5 离线 RAG 小模型知识库（替代纯本体规则问答）

- **架构**：`文档 → 切块 → 嵌入(bge-m3/Qwen3-Embedding) → LanceDB → 混合检索(BM25+向量) → Rerank(bge-reranker) → 小模型(Qwen3-1.5B/0.6B)生成（LLM 可选，先可回答确定性问答）`。
- **依赖**：`chromadb 1.5.9` 或 `lancedb 0.37.1`、`onnxruntime`（嵌入模型 ONNX）、`llama-cpp-python 0.3.34` 或 `onnxruntime-genai`（小模型）。
- **参数**：切块 `chunk_size=512, overlap=64`；嵌入 `bge-m3 dim=1024`；混合检索 `top_k=20`（BM25:向量=0.3:0.7）；Rerank `top_n=5`；`similarity_threshold=0.5`（低于则答"库中无据"防幻觉）。
- **流程**：入库（设备手册/操作规程/历史工单）→ 检索（用户问题）→ 重排 → 拼接上下文 → 小模型回答（**先查库再回答，禁幻觉**，复用 MonitorAsk 原则）。
- **数据格式**：向量条目 `{id, chunk_text, metadata:{device,type,doc}, embedding:[1024]}`；检索返回 `{text, score, metadata}`。
- **API**：
  ```python
  kb.add_docs([{"text":..., "metadata":{...}}])
  hits = kb.query("这个泵温度偏高怎么办", top_k=5)   # 混合+重排
  answer = llm.generate(prompt_with_context(hits))
  ```
- **效益**：从"结构化本体问答"扩展到"非结构化文档语义问答"，FDE 现场可离线查运维知识，且与现有 Ontology 可并存（本体管确定性、RAG 管语义）。

### 2.6 现场 Agent / 多模态 / 语音交互

- **Agent 骨架**：基于 **LangGraph**（图式状态机）或轻量自研，接入 **MCP** 暴露工具（`monitor.query`、`ticket.open`、`kb.search`、`opcua.read`）。
- **工具调用**：Qwen3 原生 function calling；结构化 JSON 输出；人机确认断点（LangGraph interrupt）。
- **多模态**：接入 **Qwen2.5-VL/Gemma 3** 小模型，现场**拍照 → 仪表 OCR / 铭牌识别 / 缺陷分类**；`mediapipe 1.0.1` 做设备二维码/标签识别。
- **语音**：
  - ASR：**`sherpa-onnx 1.13.5`**（离线，含 Silero VAD，中文 Paraformer）或 **`faster-whisper 1.2.1`**。
  - TTS：**Edge-TTS / Piper / CosyVoice**（中文，离线可 Piper）。
  - 流程：`麦克风 → VAD 断句 → sherpa-onnx ASR → 文字 → Agent 工具调用 → 结果 TTS 播放`；可用 **Pipecat/LiveKit Agents** 编排完整语音 Agent。
- **依赖**：`langgraph`、`mcp`、`sherpa-onnx 1.13.5`、`piper`。
- **数据格式**：语音对话轮次日志 `{role, text, asr_conf, intent, tool_calls:[{tool,args,result}], tts_text}`；音频 wav 16k 单声道。
- **效益**：FDE 现场不敲键盘，直接"说话查设备、拍照诊断"，大幅提升现场效率与交付体验。

### 2.7 低代码现场工具 / 实时看板

- **看板**：现有 `web/` 升级为实时仪表盘（WebSocket 推 `latest`/`alerts`），或用 **Grafana** 对接时序源。
- **规则/流**：引入 **Node-RED** 做现场流编排（MQTT/OPC-UA/HTTP 节点），或对接 **ThingsBoard Edge** 做边缘规则。
- **依赖**：`fastapi 0.141.1` + `uvicorn 0.52.3`（现有 web 栈）或容器化 Grafana/ThingsBoard。
- **数据格式**：WebSocket 事件 `{type:"metric|alert", device_id, metric, value, ts}`；仪表盘用 Prometheus/Grafana 命名或自定义 JSON。
- **效益**：交付物从"命令行+Markdown"升级为"可给甲方看的实时看板"，提升专业度与可交付性。

---

## 三、对标最新最佳实践（具体工具/产品技术细节）

### 3.1 ThingsBoard（对标 RAG/监测平台）
- **版本**：3.5-3.7+（2024-2026）；`thingsboard-gateway 3.8.4`（Python，实测）。
- **架构**：设备（Device）/资产（Asset）/租户（Tenant）；遥测（telemetry）+属性（attribute，客户端/服务端）；规则引擎（Rule Engine：msg→filter→processor→action 流）；设备配置（Device Profile）定义传输（MQTT/HTTP/CoAP/LwM2M/OPC-UA/Modbus）。
- **边缘**：**ThingsBoard Edge** 本地处理+云端同步。
- **对标启示**：solo 应借鉴其"**统一设备抽象 + 遥测 + 规则引擎 + 看板**"，但保持零依赖轻量（ThingsBoard 偏重，不适合一人公司嵌入式交付）。差异：ThingsBoard 用 Cassandra/PostgreSQL/TimescaleDB；solo 用 LanceDB/sqlite-vec。

### 3.2 EMQX（对标 MQTT5/SparkplugB）
- **版本**：EMQX 5.x（开源，完整 MQTT5）；支持规则引擎（SQL-like 转存到 MQTT/HTTP/TimescaleDB/InfluxDB）、百万连接、Sparkplug B。
- **对标启示**：solo 不造 broker，直连 EMQX（或轻量 Mosquitto/NanoMQ）；重点在**客户端侧**吃透 MQTT5 特性 + Sparkplug B 生命周期解析（见 2.4）。

### 3.3 轻量模型/现场工具对标
- **推理**：Ollama + GGUF（Qwen3-0.6B~7B）对齐 `llama-cpp-python`；OpenVINO/NNCF 对齐 ONNX 量化。
- **RAG**：对标 LanceDB/Chroma + bge-m3/Qwen3-Embedding + rerank 的标准栈。
- **现场工具**：对标 Node-RED（流）/ ThingsBoard（平台）/ Grafana（看板）——solo 定位"**单机、离线、零依赖**的轻量替代"，胜在可嵌入、可脚本化、可被甲方自持。

---

## 四、差距：solo FDE 现状 vs 最新技术（具体差距点）

| 能力域 | solo FDE 现状 | 最新技术 | 差距点（具体） |
|:--|:--|:--|:--|
| 时序存储 | JSON 文件全量重读；分钟预聚合 | LanceDB/sqlite-vec 列式；Parquet 压缩 | ① 无随机区间查询；② 高吞吐写瓶颈；③ 无压缩/保留策略 |
| 异常检测 | 阈值 + 环比中位数突变（单变量） | ML（PyOD/iTransformer/TimesNet）+ 多变量 + 周期性 + 流式 | ① 无多变量；② 无周期性/季节性建模；③ 无自适应阈值；④ 无重建误差/分数 |
| 边缘 AI | 无 ONNX 推理 | ONNX Runtime/OpenVINO + 量化 | ① 无推理运行时；② 无量化；③ 无蒸馏闭环 |
| 协议 | paho-mqtt(3.1.1)、opcua 旧库、Modbus | asyncua 2.0.1、MQTT5、Sparkplug B、OPC-UA PubSub | ① 无 MQTT5 特性；② 无 Sparkplug B；③ OPC-UA 无 PubSub/安全深化；④ opcua 库过旧 |
| 知识 | 本体规则问答（非语义） | 离线 RAG + bge-m3 + rerank + 小模型 | ① 无向量检索；② 无语义/非结构化文档；③ 无重排；④ 无 LLM 生成 |
| 智能体 | MonitorAsk 关键词路由 | LangGraph + MCP + 工具调用 + 多模态 + 语音 | ① 无 agent 编排；② 无工具协议；③ 无视觉；④ 无语音 I/O |
| 交付 | CLI + Markdown | 实时看板 + 低代码流 + 移动端 | ① 无实时看板；② 无低代码；③ 无移动端 |

---

## 五、优化方案 P0 / P1 / P2（最新技术 + 细描述，效益最大化）

> 原则：P0 = 高效益、中低投入、离线可交付、构成后续基础；P1 = 进阶智能；P2 = 规模化/先进。

### P0（先落地，效益最大，2-4 周量级）
1. **真实时序存储**：`MetricStore` 底层换 **LanceDB/sqlite-vec**，保留 `device_metric` 语义，加 `ingest_batch/range/aggregate`，加保留策略。→ 见 2.1。
2. **混合异常检测**：`AnomalyDetector` 层1（MAD/季节性/自适应阈值，零依赖先上线）+ 层2（PyOD/轻量 AE → ONNX，`onnxruntime 1.28.0`），告警复用现有工单闭环，`type="ml_anomaly"`。→ 见 2.2。
3. **协议升级**：迁移 **asyncua 2.0.1** + **paho-mqtt 2.1.0（MQTT5）** + 新增 **SparkplugSource**（生命周期解析）+ OPC-UA PubSub 订阅。→ 见 2.4。
4. **离线 RAG 知识库**：LanceDB + bge-m3/Qwen3-Embedding（ONNX）+ 混合检索 + rerank + 可选小模型生成；与 Ontology 并存。→ 见 2.5。
5. **工具调用 Agent（文本）**：LangGraph/MCP 暴露 `monitor/opcua/kb/ticket` 工具，Qwen3 原生 function calling；MonitorAsk 升级为"先查库再答 + 工具闭环"。→ 见 2.6 前半。
6. **实时看板**：`fastapi + WebSocket` 推送 `latest/alerts`，交付可看仪表盘。→ 见 2.7。

**P0 依赖清单**：`lancedb sqlite-vec onnxruntime asyncua paho-mqtt pyod langgraph mcp fastapi uvicorn`；小模型 ONNX/GGUF 由用户侧缓存。

### P1（进阶智能，+2-4 周）
1. **语音 I/O**：`sherpa-onnx 1.13.5`（离线 ASR+VAD，中文 Paraformer）+ Piper/CosyVoice TTS；语音 Agent 用 Pipecat/LiveKit。→ 见 2.6 后半。
2. **多模态视觉诊断**：Qwen2.5-VL/Gemma 3 小模型，现场拍照→仪表 OCR/铭牌识别/缺陷分类；`mediapipe` 二维码识别。→ 见 2.6。
3. **时序预测与 RUL（PHM 雏形）**：轻量 LSTM/TTM 做短期预测 + 健康指数；告警前预警。→ 见 1.3/1.5。
4. **模型量化落地**：把已训异常检测/嵌入模型 `quantize_static` int8 部署，评估精度退化。
5. **数字孪生轻量版**：glTF + Cesium/Three.js Web 端 3D 设备模型，叠加实时指标与告警（2D→3D 起步）。

### P2（规模化/先进，视需要）
1. **知识蒸馏闭环**：大模型合成数据 → 小模型续训（Qwen3-0.6B/1.5B）→ QAT int4 → 端侧部署；reverse-KL/DIST/DKD 目标。→ 见 2.3。
2. **时序 foundation 模型**：TimesFM 2.0 / Chronos 微调/蒸馏到 TTM，做高精度预测与多域泛化。
3. **GraphRAG**：本体+向量融合的知识图谱增强检索（对齐微软 GraphRAG）。
4. **低代码/平台化**：Node-RED 流 + ThingsBoard Edge 对接；多租户知识库注册（对齐现有多租户本体注册表）。
5. **AR 现场辅助**：WebXR + model-viewer，在移动端叠加设备信息/检修指引。

---

## 附：版本锚点表（PyPI 实测 2026 年中）

| 库 | 版本 | 用途 |
|:--|:--|:--|
| onnxruntime | 1.28.0 | 统一推理运行时 |
| onnxruntime-genai | 0.15.2 | 端侧 LLM |
| openvino | 2026.3.0 | Intel 加速 + NNCF |
| lancedb | 0.37.1 | 嵌入式向量/列式存储 |
| sqlite-vec | 0.1.9 | 极轻量向量索引 |
| chromadb | 1.5.9 | 向量库 |
| qdrant-client | 1.19.0 | 向量库 |
| asyncua | 2.0.1 | OPC-UA 客户端/服务器 |
| paho-mqtt | 2.1.0 | MQTT5 |
| pymodbus | 3.15.0 | Modbus |
| sherpa-onnx | 1.13.5 | 离线 ASR+VAD |
| faster-whisper | 1.2.1 | 离线 ASR |
| llama-cpp-python | 0.3.34 | GGUF 小模型 |
| pyod | 3.6.4 | 异常检测算法库 |
| river | 0.25.0 | 流式 ML |
| anomalib | 2.6.0 | 异常检测套件 |
| sktime | 1.1.0 | 时序 ML |
| torch | 2.13.0 | 训练 |
| transformers | 5.15.0 | 模型加载/蒸馏 |
| lightgbm | 4.7.0 / xgboost 3.4.1 | 树模型 |
| fastapi | 0.141.1 / uvicorn 0.52.3 | Web/WS |
| mediapipe | 1.0.1 | 视觉/感知 |
| thingsboard-gateway | 3.8.4 | 网关对接参照 |

> 说明：Web 搜索引擎在本环境被 GFW/代理污染（返回无关结果），故版本号改用 **PyPI 官方 JSON API 直接核验**（可靠、实时）；模型/规范/产品细节基于 2024-2026 最新生态知识。落地某一项时请再复验一次对应版本号。
