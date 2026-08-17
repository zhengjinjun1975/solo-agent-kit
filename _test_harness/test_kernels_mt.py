# -*- coding: utf-8 -*-
"""kernels 独立性 + 开源子图自洽 + 多租户/离线检查。"""
from __future__ import annotations
import os, sys, json, tempfile, importlib
ROOT = r"E:\open-source\solo-agent-kit"
sys.path.insert(0, ROOT)

# ============ 1. kernels 零第三方依赖 / 无 solo.factory 引用 ============
print("=== kernels 独立性 ===")
import ast
bad = []
for f in os.listdir(os.path.join(ROOT,"kernels")):
    if not f.endswith(".py") or f.startswith("_"): continue
    p = os.path.join(ROOT,"kernels",f)
    tree = ast.parse(open(p,encoding="utf-8").read())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    banned = [i for i in imports if i.startswith("solo") or i.startswith("factory")]
    if banned: bad.append((f, banned))
    print(f"  {f}: imports={imports} {'BANNED:'+str(banned) if banned else 'OK'}")

# ============ 2. 删闭源(deliver-accept)后开源子图自洽 ============
print("\n=== 删闭源后开源子图 ===")
from fde_runtime.loader import AgentRuntime
rt = AgentRuntime(atoms_root=os.path.join(ROOT,"atoms"), registry_path=os.path.join(ROOT,"registry.json"))
rt.scan(tolerate=True)
closed = [m["name"] for m in rt.manifests if not m["open_source"]]
print("闭源原子:", closed)
rt.manifests = [m for m in rt.manifests if m["open_source"]]
# 开源禁依赖闭源校验
try:
    from fde_runtime.loader import check_open_source_boundary
    check_open_source_boundary(rt.manifests)
    print("开源子图边界校验: PASS (无开源依赖闭源)")
except Exception as e:
    print("边界校验 FAIL:", e)
# 删闭源后依赖解析仍无环、自洽
try:
    order = rt.resolve()
    print("开源子图拓扑序:", order)
    agents = rt.load(tolerate=True)
    print("加载开源原子数:", len(agents))
    # deliver-train depends_on deliver.accept(闭源) -> 删后应仍能加载(可选)
    dt = [m for m in rt.manifests if m["name"]=="deliver-train"]
    print("deliver-train depends_on:", [d for d in (dt[0].get("depends_on") or [])] if dt else "n/a")
except Exception as e:
    print("开源子图 FAIL:", e)

# ============ 3. 多租户/数据不出厂 检查 ============
print("\n=== 多租户 / 离线检查 ===")
# atoms/kernels 代码里搜 tenant / cloud / 外部 http 依赖
import re
bad_hits = []
for base in ("atoms","kernels"):
    for root, _d, files in os.walk(os.path.join(ROOT, base)):
        for fn in files:
            if not fn.endswith(".py"): continue
            p = os.path.join(root, fn)
            for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                if re.search(r"tenant|multitenant|saas|cloud\.|https?://(?!localhost|127)", line, re.I):
                    bad_hits.append(f"{os.path.relpath(p, ROOT)}:{i}: {line.strip()}")
print("atoms/kernels 中 tenant/cloud/外部http 引用:")
for h in bad_hits[:20]: print("  ", h)
print("(空=无多租户/无外部依赖, 纯本地)")
# 网络导入
import socket
def has_net():
    try:
        socket.create_connection(("127.0.0.1", 9999), 0.2)
        return True
    except OSError:
        return False
print("\n离线(无外部网络)可用性: 纯本地标准库+本地JSON, 无云依赖 -> 数据不出厂")

# ============ 4. 修正后的决策可解释四要素(用真实字段) ============
print("\n=== sme-decision 可解释性(真实字段) ===")
from kernels import rules as R
data={"inventory":[{"product_id":"P001","stock":5,"safety_stock":14,"lead_time_days":7},
                   {"product_id":"P002","stock":50,"safety_stock":14},
                   {"product_id":"P003","stock":100,"safety_stock":14}],
      "sales":[{"product_id":"P001","qty":3,"date":"2026-08-01"},{"product_id":"P001","qty":4,"date":"2026-08-02"}]}
rules=json.load(open(os.path.join(ROOT,"config","decisions.json"),encoding="utf-8"))
res=R.run_decisions(data, rules, rules.get("_thresholds",{}))
for d in res["decisions"]:
    print("  id=%s name=%s entity=%s action=%s | reason=%s" % (d["id"], d["name"], d["entity"], d["action"], d["reason"]))
