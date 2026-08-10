# -*- coding: utf-8 -*-
"""example_04_factory_ontology.py — 工厂级本体建模（FDE 核心场景）。

展示真正解决工厂层级本体建模工作：
设备台账 CSV + 关系声明 → 实体关系本体 → 结构化查询/问题解答。

跑法：python examples/example_04_factory_ontology.py

体现差异化：本体优先（工厂数据）。回答"哪台空压机要维护"这类
结构化问题（零 LLM，纯本体导航），而非相似文本检索。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.ontology import Ontology

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    print("== 场景④：工厂级本体建模 ==\n")

    # 1. 读关系声明（对象属性：外键列→目标实体）
    print("[1/4] 加载工厂关系声明...")
    with open(os.path.join(DATA, "factory_relations.json"), encoding="utf-8") as f:
        rel_config = json.load(f)
    rels = rel_config["factory_equipment"]["object_properties"]
    print(f"  声明 {len(rels)} 个对象属性: "
          + ", ".join(f"{c}→{v['target_class']}" for c, v in rels.items()))

    # 2. 建本体（设备表 + 关系）
    print("[2/4] 从设备台账建本体...")
    o = Ontology()
    o.from_csv(os.path.join(DATA, "factory_equipment.csv"),
               entity_name="factory_equipment",
               id_col="id",
               relations=rels)
    o.build()
    print(f"  实体: {list(o.entities.keys())}")
    print(f"  三元组: {len(o.triples)}")

    # 3. 关系查询（实体间导航，零 LLM）
    print("[3/4] 结构化关系查询...")
    # 设备 D001 属于哪条产线
    line = o.query("factory_equipment", "D001", "line_id")
    loc = o.query("factory_equipment", "D001", "location")
    print(f"  D001(空压机) 属于: {line} | 位于: {loc}")

    # 4. 工厂问题解答（零 LLM，纯本体导航）
    print("[4/4] 工厂级问题解答...")
    q1 = o.query("factory_equipment", "D002", "device_type")
    print(f"  ① D002 是什么设备: {q1}")
    # 所有待维护的设备
    maintain = [(s.split(":")[-1], o.query("factory_equipment", s.split(":")[-1], "device_type"))
                for s, p, v in o.triples
                if p.endswith("status") and v == "待维护"]
    print(f"  ② 哪些设备要维护: {[(d, t) for d, t in maintain if t]}")
    # 空压机都哪些（对象属性导航：hasType→DeviceType:空压机）
    air = [s.split(":")[-1] for s, p, o in o.triples
           if o.endswith("DeviceType:空压机")]
    print(f"  ③ 全部空压机: {air}")

    # 导出本体（可选）
    print("\n  本体摘要:")
    print("  " + o.entity_summary().replace("\n", "\n  "))
    print("\n== 完成：工厂级本体建模 + 结构化查询 ==")
    print("说明：这些答案来自本体结构（实体关系），非文本相似度——本体优先的核心。")


if __name__ == "__main__":
    main()
