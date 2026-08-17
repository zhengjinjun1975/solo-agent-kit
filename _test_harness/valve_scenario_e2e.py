# -*- coding: utf-8 -*-
"""solo 一企一行业一数据场景端到端实测（真实数据非空壳）。

场景: 华泰阀门制造厂 (一企) / 阀门制造 (一行业) / 阀门设备+振动指标+销售 三张CSV (一数据)
链路: 数据→本体→监测→诊断→决策→写作→交付→验收，每功能真实触发+断言实际生效。
事件驱动: 灌入新数据→监测/本体/决策/交付 自动联动, 不残留旧数据不串台。
跨开源: factory/sme 联动, 依赖缺失回退。
"""
import csv, json, os, sys, tempfile, shutil

ROOT = "E:/open-source/solo-agent-kit"
sys.path.insert(0, ROOT)
DATA = os.path.join(ROOT, "_test_harness", "valve_factory")
EQUIP = os.path.join(DATA, "valve_equipment.csv")
VIB = os.path.join(DATA, "vibration_metrics.csv")
SALES = os.path.join(DATA, "valve_sales.csv")

from fde_runtime.loader import AgentRuntime

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✅ PASS  {name}  {detail}")
    else:
        FAIL.append(name)
        print(f"  ❌ FAIL  {name}  {detail}")

def load_csv(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def rows_by_metric():
    vib = load_csv(VIB)
    by = {}
    for r in vib:
        by.setdefault(r["device_id"], {}).setdefault(r["metric"], []).append(float(r["value"]))
    return by

def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

rt = AgentRuntime()
rt.scan(tolerate=True)
rt.load(tolerate=True)

print("=" * 60)
print("【0. 运行时】注册原子 / 加载 / 能力")
check("load 13 atoms", len(rt.agents) == 13, f"{len(rt.agents)}")
caps = set(rt.capabilities().keys())
for want in ["data.cap","memory.core","diagnose.kb","fde.task","monitor.device",
             "ontology.qa","sme.decision","predict.maintain","deliver.accept",
             "deliver.train","write.qa","write.evidence","evolve.self"]:
    check(f"cap {want}", want in caps)

# ---------- 1. 数据 ----------
print("\n【1. 数据】阀门设备 CSV → clean/describe/report (真实列/行)")
equip = load_csv(EQUIP)
check("读设备CSV 10行", len(equip) == 10, f"{len(equip)}")
# clean: 需要 rows 列表
d1 = rt.run_capability("data.cap", op="describe", values=[r["power_kw"] for r in equip if r["power_kw"]])
check("describe 均值真实", d1["ok"] and d1["data"]["describe"]["mean"] > 4.0,
      f"mean={d1['data']['describe']['mean']}")
d2 = rt.run_capability("data.cap", op="spc", values=[float(x) for x in [r["stock"] for r in equip]])
check("SPC 控制图判异", d2["ok"] and d2["data"]["spc"].get("judge") is not None,
      f"judge={d2['data']['spc'].get('judge')} out={len(d2['data']['spc'].get('out_of_control',[]))}")
d3 = rt.run_capability("data.cap", op="cpk", values=[float(x) for x in [r["stock"] for r in equip]], usl=100, lsl=0)
check("CPK 过程能力", d3["ok"] and d3["data"]["cpk"].get("cpk") is not None, f"cpk={d3['data']['cpk'].get('cpk')}")

# ---------- 2. 本体 ----------
print("\n【2. 本体】阀门设备 → build + ask (确定性聚合问答)")
o1 = rt.run_capability("ontology.qa", op="build", rows=equip, entity_name="阀门",
                       dir=tempfile.mkdtemp(prefix="onto_"))
check("本体建模实例数=10", o1["ok"] and len(o1["data"]["ontology"]["instances"]) == 10)
q1 = rt.run_capability("ontology.qa", op="ask", rows=equip, question="阀门一共有多少条")
check("本体问答 count=10", q1["ok"] and q1["data"]["answer"]["value"] == 10,
      f"value={q1['data']['answer']['value']}")
q2 = rt.run_capability("ontology.qa", op="ask", rows=equip, question="状态为故障的阀门")
check("本体问答 filter 故障=1", q2["ok"] and q2["data"]["answer"].get("value") == 1,
      f"value={q2['data']['answer'].get('value')} answer={q2['data']['answer'].get('answer')}")
# 行业本体联动: 阀门制造行业 col_cn 映射
from solo.factory.industry import load_industry  # noqa
ind = load_industry("阀门制造")
check("行业col_cn 阀门类型映射", isinstance(ind.get("col_cn", {}).get("valve_type"), str),
      f"valve_type→{ind.get('col_cn',{}).get('valve_type')}")

# ---------- 3. 监测 ----------
print("\n【3. 监测】振动指标 → ingest/adaptive/anomaly/evaluate (真实越限检测)")
mon_dir = tempfile.mkdtemp(prefix="mon_")
vib_by = rows_by_metric()
v1_pts = []
for i, v in enumerate(vib_by["V001"]["vibration"]):
    v1_pts.append({"device_id": "V001", "metric": "vibration", "value": v,
                   "ts": f"2026-08-16T10:{i:02d}:00"})
m1 = rt.run_capability("monitor.device", op="ingest", dir=mon_dir, points=v1_pts)
check("监测 ingest 8点", m1["ok"] and m1["data"]["ingested"]["count"] == 8,
      f"count={m1['data']['ingested']['count']}")
m2 = rt.run_capability("monitor.device", op="adaptive", dir=mon_dir,
                       device_id="V001", metric="vibration", k=3.0)
upper = m2["data"]["threshold"].get("upper")
check("动态阈值MAD上界<8.6", m2["ok"] and upper and upper < 8.6, f"upper={upper}")
m3 = rt.run_capability("monitor.device", op="anomaly", dir=mon_dir,
                       device_id="V001", metric="vibration", k=3.0)
check("异常检测检出8.6", m3["ok"] and any(a.get("value") == 8.6 for a in m3["data"]["anomalies"]),
      f"n={len(m3['data']['anomalies'])}")
m4 = rt.run_capability("monitor.device", op="set_rule", dir=mon_dir,
                       device_id="V001", metric="vibration",
                       rule={"cmp_op": ">", "threshold": upper, "level": "critical"})
check("告警规则设置", m4["ok"] and m4["data"]["rules"])
m5 = rt.run_capability("monitor.device", op="evaluate", dir=mon_dir,
                       device_id="V001", metric="vibration", value=8.6)
check("越限评估触发告警", m5["ok"] and m5["data"]["alerts"] and m5["data"]["worst_level"] == "critical",
      f"worst={m5['data']['worst_level']} alerts={len(m5['data']['alerts'])}")

# ---------- 4. 诊断 ----------
print("\n【4. 诊断】故障知识库 → learn + search (根因+防幻觉)")
kb_dir = tempfile.mkdtemp(prefix="kb_")
k1 = rt.run_capability("diagnose.kb", op="add", dir=kb_dir,
                       problem="阀门振动越限", solution="检查轴承磨损/阀杆对中",
                       signals=["vibration"])
check("知识库learn", k1["ok"])
k2 = rt.run_capability("diagnose.kb", op="search", dir=kb_dir, problem="振动越限", top_k=3)
check("知识库命中根因", k2["ok"] and k2["data"]["hit"] and "轴承" in k2["data"]["hit"]["solution"],
      f"sol={k2['data']['hit']['solution'] if k2['data']['hit'] else None}")
k3 = rt.run_capability("diagnose.kb", op="search", dir=kb_dir, problem="完全无关的XXX主题", top_k=3)
check("知识库防幻觉诚实miss", k3["ok"] and k3["data"]["hit"] is None,
      f"hit={k3['data']['hit']}")

# ---------- 5. 决策 ----------
print("\n【5. 决策】SME 阈值决策 (阀门制造行业阈值覆盖)")
dec_data = {
    "inventory": [{"product_id": r["id"], "stock": float(r["stock"]),
                   "safety_stock": float(r["safety_stock"]),
                   "lead_time_days": float(r["lead_time_days"])} for r in equip],
    "sales": load_csv(SALES),
    "equipment": [{"id": r["id"], "status": r["status"], "install_date": r["install_date"],
                   "warranty_months": 36} for r in equip],
}
dec1 = rt.run_capability("sme.decision", op="decide", data=dec_data, industry="阀门制造")
check("决策产出", dec1["ok"] and dec1["data"]["decisions"])
dnames = [d["name"] for d in dec1["data"]["decisions"]]
check("库存补货决策命中(V003库存8<reorder)", any("补货" in n for n in dnames), f"{sorted(set(dnames))}")
# 阀门行业 safety_stock=30 覆盖默认14
check("行业阈值覆盖(safety=30)", dec1["data"]["thresholds"].get("inventory", {}).get("safety_stock") == 30,
      f"thr={dec1['data']['thresholds'].get('inventory',{})}")

# ---------- 6. 写作 ----------
print("\n【6. 写作】write-qa 六维 + write-evidence 证据核查")
rep_text = "华泰阀门制造厂振动预警已上线，V001振动值8.6时自动告警并开工单，建议更换轴承并做动平衡。阀门安全库存为30个。"
w1 = rt.run_capability("write.qa", op="scan", text=rep_text)
check("六维写作扫描", w1["ok"] and w1["data"]["report"].get("passed") is not None,
      f"fail_count={w1['data']['report'].get('fail_count')} passed={w1['data']['report'].get('passed')}")
w2 = rt.run_capability("write.evidence", op="fact_check", text=rep_text,
                       source_rows=[{"device_id": "V001", "vibration": 8.6, "metric": "vibration"},
                                    {"valve": "V001", "safety_stock": 30}])
check("证据核查全可溯源", w2["ok"] and w2["data"]["summary"].get("verdict") == "全可溯源",
      f"verdict={w2['data']['summary'].get('verdict')}")

# ---------- 7. 交付 + 验收 ----------
print("\n【7. 交付+验收】deliver-accept: 需求→SRS→验收→勾稽→交付包→verify")
acc_dir = tempfile.mkdtemp(prefix="acc_")
reqs = [
    {"id": "R-001", "title": "振动预警", "category": "设备", "story": "V001振动越限自动预警", "priority": "P0",
     "acceptance": ["振动越限可观测"]},
    {"id": "R-002", "title": "库存决策", "category": "采购", "story": "阀门安全库存自动补货建议", "priority": "P1",
     "acceptance": ["补货建议可生成"]},
]
a1 = rt.run_capability("deliver.accept", op="srs", dir=acc_dir, requirements=reqs, title="华泰阀门运维系统SRS")
check("SRS生成", a1["ok"] and a1["data"]["srs"]["req_n"] == 2, f"req_n={a1['data']['srs']['req_n']}")
a2 = rt.run_capability("deliver.accept", op="acceptance", dir=acc_dir, requirements=reqs)
alist = a2["data"]["acceptance_list"]
for it in alist:
    it["result"] = "通过"
check("验收清单", a2["ok"] and len(alist) >= 2)
a3 = rt.run_capability("deliver.accept", op="reconcile", dir=acc_dir, requirements=reqs, acceptance=alist)
check("勾稽一致", a3["ok"] and a3["data"]["reconcile"].get("ok") is True)
a4 = rt.run_capability("deliver.accept", op="package", dir=acc_dir, requirements=reqs, acceptance=alist,
                       monitor_snapshot={"devices": ["V001","V003","V004"]},
                       tickets=[{"id": "TK-001", "state": "open", "problem": "振动越限"}],
                       kb="valve", industry="阀门制造", hit=0.9, questions_n=10, hits=9)
check("交付包生成", a4["ok"] and a4["data"]["package"]["report"]["markdown"] and a4["data"]["package"]["tickets"])
check("交付包验收全过", a4["data"]["accept"].get("accept") is True, f"accept={a4['data']['accept']}")
a5 = rt.run_capability("deliver.accept", op="verify", dir=acc_dir, acceptance=alist)
check("验收verify", a5["ok"] and a5["data"]["accept"]["accept"] is True)

# ---------- 8. 工单状态机 ----------
print("\n【8. 工单】fde-task issue→diagnose→resolve→verify→audit")
tk_dir = tempfile.mkdtemp(prefix="tk_")
t1 = rt.run_capability("fde.task", op="issue", dir=tk_dir, problem="V001振动越限", severity="high")
tid = t1["data"]["ticket"]["id"]
check("工单创建 open", t1["ok"] and t1["data"]["ticket"]["state"] == "open", tid)
t2 = rt.run_capability("fde.task", op="diagnose", dir=tk_dir, tid=tid, diagnosis="轴承磨损")
check("工单诊断 diagnosed", t2["ok"] and t2["data"]["ticket"]["state"] == "diagnosed")
t3 = rt.run_capability("fde.task", op="resolve", dir=tk_dir, tid=tid, resolution="更换轴承")
check("工单解决 resolved", t3["ok"] and t3["data"]["ticket"]["state"] == "resolved")
t4 = rt.run_capability("fde.task", op="verify", dir=tk_dir, tid=tid)
check("工单验收 verified", t4["ok"] and t4["data"]["ticket"]["state"] == "verified")
t5 = rt.run_capability("fde.task", op="audit", dir=tk_dir, tid=tid)
check("审计留痕≥4", t5["ok"] and len(t5["data"]["audit_trail"]) >= 4, f"{len(t5['data']['audit_trail'])}")

print("\n" + "=" * 60)
print(f"场景端到端: {len(PASS)} PASS / {len(FAIL)} FAIL")
if FAIL:
    print("FAIL:", FAIL)
    sys.exit(1)
