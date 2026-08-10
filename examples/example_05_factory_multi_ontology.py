# -*- coding: utf-8 -*-
"""example_05_factory_multi_ontology.py — 多表工厂本体（设备+工单关联）。

展示真正解决工厂层级的跨实体建模：
设备台账 + 工单 → 关系本体 → 跨实体问题解答（哪些高优先工单关联哪些设备）。

跑法：python examples/example_05_factory_multi_ontology.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo.ontology import Ontology

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def main():
    print("== 场景⑤：多表工厂本体（设备 + 工单关联） ==\n")

    # 1. 加载关系声明
    print("[1/4] 加载多表关系声明...")
    with open(os.path.join(DATA, "factory_relations.json"), encoding="utf-8") as f:
        rel_config = json.load(f)
    print(f"  设备表关系: {list(rel_config['factory_equipment']['object_properties'].keys())}")
    print(f"  工单表关系: {list(rel_config['factory_workorders']['object_properties'].keys())}")

    # 2. 建多表本体
    print("[2/4] 建多表本体...")
    o = Ontology()
    o.from_csv(os.path.join(DATA, "factory_equipment.csv"),
               entity_name="factory_equipment", id_col="id",
               relations=rel_config["factory_equipment"]["object_properties"])
    o.from_csv(os.path.join(DATA, "factory_workorders.csv"),
               entity_name="factory_workorders", id_col="wo_id",
               relations=rel_config["factory_workorders"]["object_properties"])
    o.build()
    print(f"  实体: {list(o.entities.keys())}")
    print(f"  三元组: {len(o.triples)}")

    # 3. 跨实体查询：工单→设备→设备属性
    print("[3/4] 跨实体关系导航...")
    # W001 工单关联哪个设备
    eq = o.query("factory_workorders", "W001", "equipment_id")
    print(f"  W001 工单关联设备: {eq}")
    # 关联设备是什么类型（跨实体导航）
    if eq and eq[0].startswith("factory_equipment:"):
        dev_id = eq[0].split(":")[-1]
        dev_type = o.query("factory_equipment", dev_id, "device_type")
        print(f"  W001 关联的 {dev_id} 设备类型: {dev_type}")

    # 4. 多表问题解答：高优先工单涉及哪些设备
    print("[4/4] 多表问题解答...")
    # 高优先工单
    high_wo = [s.split(":")[-1] for s, p, v in o.triples
               if s.startswith("factory_workorders:") and p.endswith("priority") and v == "高"]
    print(f"  ① 高优先工单: {high_wo}")
    # 每个高优先工单关联的设备
    for wo in high_wo:
        dev = o.query("factory_workorders", wo, "equipment_id")
        if dev:
            dev_id = dev[0].split(":")[-1]
            d_type = o.query("factory_equipment", dev_id, "device_type")
            print(f"     {wo} → 设备 {dev_id}({d_type[0].split(':')[-1] if d_type else '?'})")

    print("\n== 完成：多表工厂本体 + 跨实体解答 ==")
    print("说明：工单→设备→设备类型的关联查询，全程本体结构导航，零 LLM。")


if __name__ == "__main__":
    main()
