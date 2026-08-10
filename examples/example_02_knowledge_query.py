# -*- coding: utf-8 -*-
"""example_02_knowledge_query.py — 一人公司场景②：查记忆/知识。

展示本体优先 + 三层两域记忆的检索闭环：CSV 建本体 → 语义检索 → 记忆补全。
跑法：python examples/example_02_knowledge_query.py "查询词"

体现"本体优先"差异化：同一批数据，本体能回答"实体间关系"而非仅"相似文本"。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import memory as memory_mod
from solo.factory import ontology as ontology_mod


def main(query: str):
    print(f"== 场景②：查知识「{query}」 ==\n")

    # 1. 用示例数据建本体（本体优先核心）
    print("[1/3] 从示例 CSV 建本体...")
    tmp = tempfile.mkdtemp(prefix="solo-example-")
    csv_path = os.path.join(tmp, "company.csv")
    # 一人公司示例数据（合成，非真实）
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("product,customer,status\n"
                "本体问答框架,阀门厂,交付中\n"
                "经营决策平台,食品厂,研发中\n"
                "写作检查器,自媒体,已上线\n")
    o = ontology_mod.Ontology()
    o.from_csv(csv_path, entity_name="company")

    # 2. 本体检索（结构化命中）
    print("[2/3] 本体语义检索...")
    hits = o.search(query, top_k=3)
    if hits:
        print("  【本体】命中实体关系：")
        for s, p, val in hits:
            print(f"    {s} → {p} = {val}")
    else:
        print("  【本体】无结构命中，退记忆检索")

    # 3. 记忆补全（语义检索）
    print("[3/3] 记忆层检索补全...")
    m = memory_mod.Memory()
    facts = m.search(query, top_k=3)
    if facts:
        for f in facts:
            print(f"  【记忆】{f['text'][:50]}")
    else:
        print("  【记忆】暂无相关事实（可先 solo run 积累）")

    print("\n== 完成：本体优先检索 ==")
    print("说明：本体回答'实体间关系'(结构化)，记忆回答'相关事实'(语义)，两层互补。")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "阀门厂"
    main(query)
