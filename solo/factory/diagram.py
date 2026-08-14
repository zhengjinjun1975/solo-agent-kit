# -*- coding: utf-8 -*-
"""diagram.py — FDE 图件（ER 图 / 流程图 / 状态图）纯展示层。

纯展示层，零第三方依赖（对齐 svg-info-diagrams 方法论）：消费已有数据
（ontology 实体/关系、survey 生命周期阶段、task 任务状态），产出 Mermaid
源码字符串。不新增数据模型，只做「已有知识 → 图件」的序列化。

对齐 FDE 交付链：
  ontology ──实体关系──→ ER 图（数据建模可视化）
  survey   ──需求阶段──→ 流程图（需求→验收交付链路）
  task     ──任务状态──→ 状态图（工单闭环可视化）

用法：
    from solo.factory import diagram
    print(diagram.er_diagram(ont))        # 消费 ontology.triples/relations
    print(diagram.flow_diagram(phases))   # 消费 survey.PHASES
    print(diagram.state_diagram(states))  # 消费 task.STATES
"""
from __future__ import annotations

# survey 生命周期阶段（与 survey.py.PHASES 对齐，避免反向 import）
_DEFAULT_PHASES = ("采集", "结构化", "SRS", "验收")
# task 状态机（与 task.py.STATES 对齐）
_DEFAULT_STATES = ("todo", "doing", "waiting", "done", "cancelled")


def _safe_label(s: str) -> str:
    """清洗节点名（Mermaid 语法安全：去引号/冒号/括号）。"""
    return str(s).replace('"', "").replace(":", " ").replace("(", "").replace(")", "").strip() or "node"


def er_diagram(ontology, title: str = "本体实体关系图") -> str:
    """从 ontology 产出 Mermaid ER 图源码。

    消费 ontology.entities（实体→列/类型）与 ontology.relations（实体→列→目标实体）。
    对象属性（外键）渲染为关系边，属性列渲染进实体块。零第三方依赖。
    """
    lines = ["erDiagram", f"    %% {title} —— 由 factory.diagram 生成"]
    entities = getattr(ontology, "entities", {}) or {}
    relations = getattr(ontology, "relations", {}) or {}

    # 实体块：实体名 + 属性列（类型映射到 Mermaid ER 类型）
    for name, ent in entities.items():
        ent_safe = _safe_label(name)
        cols = ent.get("cols") or list((ent.get("types") or {}).keys())
        lines.append(f"    {ent_safe} {{")
        for c in cols[:12]:  # 限制列数防图过大
            ctype = _type_to_er(ent.get("types", {}).get(c))
            lines.append(f"        {ctype} {_safe_label(c)}")
        if not cols:
            lines.append("        string id")
        lines.append("    }")

    # 关系边：relations[entity][col] -> {target_class, label}
    drawn = set()
    for ent, rels in relations.items():
        for col, cfg in rels.items():
            target = cfg.get("target_class", "")
            label = cfg.get("label", col)
            src, dst = _safe_label(ent), _safe_label(target)
            if not target or (src, dst) in drawn:
                continue
            drawn.add((src, dst))
            lines.append(f'    {src} ||--o{{ {dst} : "{_safe_label(label)}"')
    return "\n".join(lines) + "\n"


def _type_to_er(t: str) -> str:
    """data 类型 → Mermaid ER 类型。"""
    return {
        "integer": "int", "float": "float", "date": "datetime", "boolean": "bool",
    }.get(t, "string")


def flow_diagram(phases: tuple = None, title: str = "FDE 交付链路") -> str:
    """从 survey 阶段产出 Mermaid 流程图源码。

    phases: 生命周期阶段元组（缺省用 survey 标准四阶段）。消费 survey.PHASES。
    """
    phases = phases or _DEFAULT_PHASES
    lines = ["flowchart LR"]
    lines.append(f"    %% {title} —— 需求→验收交付链路")
    for i, ph in enumerate(phases):
        n = _safe_label(ph)
        if i == 0:
            lines.append(f"    S[{n}]")
        elif i == len(phases) - 1:
            lines.append(f"    E[{n}]")
        else:
            lines.append(f"    N{i}[{n}]")
    # 连线
    nodes = ["S"] + [f"N{i}" for i in range(1, len(phases) - 1)] + ["E"]
    for a, b in zip(nodes, nodes[1:]):
        lines.append(f"    {a} --> {b}")
    return "\n".join(lines) + "\n"


def state_diagram(states: tuple = None, title: str = "工单状态机") -> str:
    """从 task 状态产出 Mermaid 状态图源码。

    states: 状态元组（缺省用 task 标准五态）。消费 task.STATES。
    """
    states = states or _DEFAULT_STATES
    lines = ["stateDiagram-v2"]
    lines.append(f"    %% {title} —— 长任务外置状态")
    lines.append(f"    [*] --> {_safe_label(states[0])}")
    for a, b in zip(states, states[1:]):
        lines.append(f"    {_safe_label(a)} --> {_safe_label(b)}")
    lines.append(f"    {_safe_label(states[-1])} --> [*]")
    return "\n".join(lines) + "\n"


def build(ontology=None, phases: tuple = None, states: tuple = None) -> dict:
    """一键产出三张图（ER/流程/状态），对齐 FDE 三条交付链。

    全部可缺省：ontology 缺省时 ER 图为空模板；phases/states 缺省用标准默认。
    返回 {er, flow, state} Mermaid 源码串，前端直接渲染。
    """
    return {
        "er": er_diagram(ontology) if ontology is not None else _empty_er(),
        "flow": flow_diagram(phases),
        "state": state_diagram(states),
    }


def _empty_er() -> str:
    return "erDiagram\n    %% 无本体数据（先 build_ontology 建模）\n"
