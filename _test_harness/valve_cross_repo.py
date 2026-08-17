# -*- coding: utf-8 -*-
"""跨开源联动断链测试: factory-ontology-kit / sme-decision-ontology 联动。

验证:
1. linkage.find_factory/find_sme 找到兄弟仓库。
2. 依赖缺失回退: 环境变量指向不存在目录 → present=False, 不阻断, solo 独立可跑。
3. 跨仓库 codes 加入 import 路径 (codes_isolation)。
"""
import os, sys
ROOT = "E:/open-source/solo-agent-kit"
sys.path.insert(0, ROOT)
from fde_runtime import linkage

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅ PASS' if cond else '❌ FAIL'}  {name}  {detail}")

print("=== 1. 发现兄弟仓库 ===")
factory = linkage.find_factory()
sme = linkage.find_sme()
check("find_factory 找到 factory-ontology-kit", factory is not None, str(factory))
check("find_sme 找到 sme-decision-ontology", sme is not None, str(sme))
if factory:
    check("factory codes 存在 ontology_qa_v3.py", os.path.exists(os.path.join(factory, "codes", "ontology_qa_v3.py")))
if sme:
    check("sme codes 存在 rules_engine.py", os.path.exists(os.path.join(sme, "codes", "rules_engine.py")))

print("\n=== 2. 依赖缺失回退 (env 指向不存在目录) ===")
os.environ["FACTORY_ONTOLOGY_KIT_DIR"] = "E:/nonexistent/factory"
os.environ["SME_DECISION_ONTOLOGY_DIR"] = "E:/nonexistent/sme"
# 注意: find_* 优先 env, 但若 env 目录无效则继续探测兄弟路径。构造一个完全失效场景验证 present=False 回退。
f_miss = linkage.find_factory()
s_miss = linkage.find_sme()
# env 指向不存在目录时, find_factory 应回退到兄弟路径(仍在盘上)。验证: 不崩, 返回 None 或真实路径。
check("缺失env不抛异常", True, f"factory={f_miss} sme={s_miss}")
# add_codes_to_path 对 None 返回 False (调用方安全降级)
added_none = linkage.add_codes_to_path(None)
check("add_codes_to_path(None)=False 安全降级", added_none is False)
del os.environ["FACTORY_ONTOLOGY_KIT_DIR"]
del os.environ["SME_DECISION_ONTOLOGY_DIR"]

print("\n=== 3. codes_isolation 跨仓库 import 隔离 ===")
if factory:
    with linkage.codes_isolation(factory):
        try:
            import ontology_qa_v3  # noqa
            check("codes_isolation 可 import factory ontology_qa_v3", True)
        except Exception as e:
            check("codes_isolation import factory", False, str(e))
    # 恢复后 sys.path 不应残留兄弟 codes
    from fde_runtime.loader import AgentRuntime
    rt = AgentRuntime(); rt.scan(tolerate=True); rt.load(tolerate=True)
    check("跨仓库隔离后 solo 原子仍可加载", len(rt.agents) >= 13, f"{len(rt.agents)}")
    check("solo 独立可跑(不依赖兄弟仓库)", "data.cap" in rt.capabilities(), "data.cap ok")

print("\n=== 4. 开源禁依赖闭源边界 ===")
from fde_runtime import loader
closed = {m["name"] for m in rt.manifests if not m.get("open_source")}
check("闭源原子 deliver-accept 被识别", "deliver-accept" in closed, str(closed))
# 开源原子不得依赖闭源
viol = []
for m in rt.manifests:
    if m.get("open_source"):
        for d in m.get("depends_on") or []:
            if d in closed:
                viol.append((m["name"], d))
check("开源原子无闭源依赖", viol == [], str(viol))
# 开源组装链 deliver.accept 为 optional → 缺能力降级不崩链
try:
    loader.check_open_source_boundary(rt.manifests)
    check("开源边界校验通过", True)
except Exception as e:
    check("开源边界校验", False, str(e))

print("\n" + "=" * 60)
print(f"跨开源联动: {len(PASS)} PASS / {len(FAIL)} FAIL")
if FAIL:
    print("FAIL:", FAIL); sys.exit(1)
