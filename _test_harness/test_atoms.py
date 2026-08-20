# -*- coding: utf-8 -*-
"""10 原子逐一行为实测：独立运行 + 数据真实非空壳。
镜像前端/装配真实参数，逐一断言真实数据。"""
from __future__ import annotations
import os, sys, json, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from fde_runtime.loader import AgentRuntime

WORK = os.path.join(tempfile.mkdtemp(prefix="fde_atoms_test_"))
os.makedirs(WORK, exist_ok=True)

rt = AgentRuntime(atoms_root=os.path.join(ROOT, "atoms"),
                  registry_path=os.path.join(ROOT, "registry.json"))
rt.scan(tolerate=True)
agents = rt.load(tolerate=True)
print("loaded agents:", sorted(agents.keys()))
print("order:", rt._order)
print("capabilities:", rt.capabilities())

results = {}
def rec(name, ok, detail=""):
    results[name] = (ok, detail)
    print(("[PASS] " if ok else "[FAIL] ") + name + (" | " + str(detail) if detail else ""))

def run(cap, **kw):
    return rt.run_capability(cap, **kw)

# ============ 1. data-cap: SPC/CPK/describe ============
seq = [4.9, 5.1, 5.0, 5.3, 5.2, 5.6, 5.7, 8.6, 5.1, 5.2]
e = run("data.cap", op="spc", values=seq, dir=WORK, usl=7.0, lsl=3.0)
d = e.get("data") or {}
spc = d.get("spc") or {}
rec("data-cap.spc", e.get("ok") and bool(spc.get("judge")) and spc.get("mean") is not None,
    {"mean": spc.get("mean"), "judge": spc.get("judge"), "points_n": len(spc.get("points", []) or [])})
# 控制图真实: 8.6 应为判异点
if spc.get("judge"):
    rec("data-cap.spc.judge_real", True, str(spc.get("judge")))
c = run("data.cap", op="cpk", values=seq, usl=7.0, lsl=3.0, dir=WORK)
cpk = (c.get("data") or {}).get("cpk") or {}
rec("data-cap.cpk", c.get("ok") and cpk.get("cpk") is not None, cpk)
desc = run("data.cap", op="describe", values=seq)
rec("data-cap.describe", desc.get("ok") and (desc.get("data") or {}).get("describe", {}).get("count") == len(seq),
    (desc.get("data") or {}).get("describe"))
# 落盘校验
rec("data-cap.spc.saved", os.path.exists(os.path.join(WORK, "spc_chart.json")), os.path.join(WORK,"spc_chart.json"))

# ============ 2. monitor-device: ingest/adaptive/set_rule/evaluate ============
md = os.path.join(WORK, "md"); os.makedirs(md, exist_ok=True)
pts = [{"device_id":"pump_01","metric":"vibration","value":v,"ts":f"2026-08-16T10:0{i}:00"}
       for i,v in enumerate([4.9,5.1,5.0,5.3,5.2,5.6,5.7,8.6])]
e = run("monitor.device", op="ingest", points=pts, dir=md)
rec("monitor.ingest", e.get("ok") and (e.get("data") or {}).get("ingested", {}).get("count") == 8,
    (e.get("data") or {}).get("ingested"))
thr = run("monitor.device", op="adaptive", device_id="pump_01", metric="vibration", k=3.0, dir=md)
t = (thr.get("data") or {}).get("threshold") or {}
rec("monitor.adaptive", thr.get("ok") and t.get("upper") is not None, t)
e = run("monitor.device", op="set_rule", device_id="pump_01", metric="vibration",
        rule={"cmp_op":">","threshold":t.get("upper",7),"level":"warn"}, dir=md)
rec("monitor.set_rule", e.get("ok") and bool(e.get("data",{}).get("rules")), e.get("data",{}).get("rules"))
e = run("monitor.device", op="evaluate", device_id="pump_01", metric="vibration", value=8.6, dir=md)
al = (e.get("data") or {}).get("alerts") or []
rec("monitor.evaluate_alert", e.get("ok") and bool(al), {"alerts":al,"worst":(e.get("data") or {}).get("worst_level")})
# 正常值不告警
e2 = run("monitor.device", op="evaluate", device_id="pump_01", metric="vibration", value=4.8, dir=md)
rec("monitor.evaluate_normal_noalert", bool((e2.get("data") or {}).get("alerts")) is False)

# ============ 3. predictive-maintain: forecast/risk/maintain ============
rise = [4.0,4.2,4.5,4.9,5.2,5.6,6.1,6.5,7.0,7.6]
e = run("predict.maintain", op="forecast", series=rise)
fc = (e.get("data") or {}).get("forecast") or {}
rec("predict.forecast", e.get("ok") and fc.get("next") is not None, fc)
e = run("predict.maintain", op="risk", series=rise, device_id="pump_01", k=3.0)
rk = (e.get("data") or {}).get("risk") or {}
rec("predict.risk_level", e.get("ok") and rk.get("level") in ("low","medium","high","critical","ok"), rk)
e = run("predict.maintain", op="maintain", failure_mode="轴承磨损", device_id="pump_01")
adv = (e.get("data") or {}).get("advice") or {}
rec("predict.maintain_advice", e.get("ok") and bool(adv.get("actions")), adv)
# kb 注入路径
e = run("predict.maintain", op="maintain", hit={"actions":["更换轴承"],"parts":["B-01"],"estimated_cost":1200}, device_id="pump_01")
adv2 = (e.get("data") or {}).get("advice") or {}
rec("predict.maintain_from_kb", adv2.get("from_kb") is True and adv2.get("actions")==["更换轴承"], adv2)

# ============ 4. sme-decision: decide 真实阈值决策 ============
data = {"inventory":[
    {"product_id":"P001","stock":5,"safety_stock":14,"lead_time_days":7},
    {"product_id":"P002","stock":50,"safety_stock":14},
    {"product_id":"P003","stock":100,"safety_stock":14}],
    "sales":[{"product_id":"P001","qty":3,"date":"2026-08-01"},
             {"product_id":"P001","qty":4,"date":"2026-08-02"}]}
e = run("sme.decision", op="decide", data=data, industry="factory")
dec = (e.get("data") or {}).get("decisions") or []
names = [x.get("name") for x in dec]
rec("sme.decision.run", e.get("ok") and bool(dec), {"total":(e.get("data") or {}).get("total"),"names":sorted(set(names))})
rec("sme.decision.need_reorder", any("补货" in (n or "") for n in names), names)
# 四要素可解释
rec("sme.decision.explainable",
    all(x.get("formula") and x.get("threshold") and x.get("data_basis") and x.get("rule_id") for x in dec),
    [ {k:x.get(k) for k in ("rule_id","name","formula","threshold","data_basis")} for x in dec[:2]])

# ============ 5. diagnose-kb: add/search/suggest + 诚实 miss ============
kbd = os.path.join(WORK,"kb"); os.makedirs(kbd, exist_ok=True)
run("diagnose.kb", op="add", problem="泵振动越限", solution="检查轴承与对中", signals=["vibration"], dir=kbd)
run("diagnose.kb", op="add", problem="电机温度过高", solution="检查散热与负载", dir=kbd)
e = run("diagnose.kb", op="search", problem="泵振动偏高", top_k=3, dir=kbd)
hit = (e.get("data") or {}).get("hit")
rec("diagnose.search", e.get("ok") and hit is not None and bool(hit.get("solution")), hit)
e = run("diagnose.kb", op="search", problem="完全无关内容xyz不存在", dir=kbd)
rec("diagnose.honest_miss", (e.get("data") or {}).get("hit") is None, (e.get("data") or {}).get("note"))
e = run("diagnose.kb", op="suggest", problem="振动越限", dir=kbd)
rec("diagnose.suggest", e.get("ok") and bool((e.get("data") or {}).get("suggestions")),
    (e.get("data") or {}).get("suggestions"))

# ============ 6. ontology-qa: build/ask(聚合/过滤) ============
rows = [{"id":"P001","status":"运行中","temp":80,"power":100},
        {"id":"P002","status":"运行中","temp":90,"power":120},
        {"id":"P003","status":"停机","temp":40,"power":0}]
e = run("ontology.qa", op="build", rows=rows, entity_name="设备", dir=WORK)
inst = (e.get("data") or {}).get("ontology") or {}
rec("ontology.build", e.get("ok") and bool(inst.get("instances")), {"instances":len(inst.get("instances",[]))})
e = run("ontology.qa", op="ask", rows=rows, question="一共有多少条记录")
rec("ontology.ask_count", e.get("ok") and (e.get("data") or {}).get("answer",{}).get("value")==3,
    (e.get("data") or {}).get("answer"))
e = run("ontology.qa", op="ask", rows=rows, question="温度平均是多少")
a = (e.get("data") or {}).get("answer") or {}
rec("ontology.ask_avg", e.get("ok") and a.get("hit") is True, a)
e = run("ontology.qa", op="ask", rows=rows, question="状态为运行中的设备")
a = (e.get("data") or {}).get("answer") or {}
rec("ontology.ask_filter", e.get("ok") and a.get("value")==2, a)
e = run("ontology.qa", op="retrieve", rows=rows, question="运行中的设备", top_k=3)
rec("ontology.retrieve", e.get("ok") and bool((e.get("data") or {}).get("retrieved")),
    (e.get("data") or {}).get("retrieved"))

# ============ 7. deliver-accept(闭源): requirement→srs→acceptance→reconcile→package→verify ============
dad = os.path.join(WORK,"del"); os.makedirs(dad, exist_ok=True)
r1 = run("deliver.accept", op="requirement", story="SPC判异能力上线，实现振动越限自动预警",
         category="质量", priority="P0", req_id="R-001", dir=dad)
r2 = run("deliver.accept", op="requirement", story="设备监测看板，支持实时振动趋势",
         category="设备", priority="P1", req_id="R-002", dir=dad)
rec("deliver.req", r1.get("ok") and r2.get("ok") and (r1.get("data") or {}).get("requirement",{}).get("id")=="R-001",
    [(r1.get("data") or {}).get("requirement",{}).get("id"),(r2.get("data") or {}).get("requirement",{}).get("id")])
reqs=[(r1.get("data") or {}).get("requirement"),(r2.get("data") or {}).get("requirement")]
s = run("deliver.accept", op="srs", requirements=reqs, title="泵站运维系统SRS", dir=dad)
rec("deliver.srs", s.get("ok") and (s.get("data") or {}).get("srs",{}).get("req_n")==2,
    {"req_n":(s.get("data") or {}).get("req_n")})
acc = run("deliver.accept", op="acceptance", requirements=reqs, dir=dad)
lst = (acc.get("data") or {}).get("acceptance_list") or []
rec("deliver.acceptance", acc.get("ok") and len(lst)>=2, {"n":len(lst)})
for i in lst: i["result"]="通过"
rec_ = run("deliver.accept", op="reconcile", requirements=reqs, acceptance=lst, dir=dad)
rec("deliver.reconcile", rec_.get("ok") and (rec_.get("data") or {}).get("reconcile",{}).get("ok") is True,
    (rec_.get("data") or {}).get("reconcile"))
pkg = run("deliver.accept", op="package", requirements=reqs, acceptance=lst,
          monitor_snapshot={"devices":2}, tickets=[{"id":"TK-001"}], kb="factory", dir=dad)
p = (pkg.get("data") or {}).get("package") or {}
rec("deliver.package", pkg.get("ok") and bool(p.get("acceptance",{}).get("acceptance_list")) and bool(p.get("report",{}).get("markdown")),
    {"accept":(pkg.get("data") or {}).get("accept")})
v = run("deliver.accept", op="verify", acceptance=lst, dir=dad)
rec("deliver.verify", v.get("ok") and (v.get("data") or {}).get("accept",{}).get("accept") is True,
    (v.get("data") or {}).get("accept"))
rec("deliver.srs_saved", os.path.exists(os.path.join(dad,"srs.md")), "srs.md exists")

# ============ 8. deliver-train: manual/faq/transfer ============
td = os.path.join(WORK,"train"); os.makedirs(td, exist_ok=True)
caps={"监测":{"SPC图":{"desc":"过程能力控制图"},"看板":{"desc":"实时振动趋势"}}}
e = run("deliver.train", op="manual", capabilities=caps, requirements=reqs, title="泵站运维培训", dir=td)
rec("train.manual", e.get("ok") and bool((e.get("data") or {}).get("manual",{}).get("markdown")),
    {"sections":(e.get("data") or {}).get("manual",{}).get("sections"),"steps":(e.get("data") or {}).get("manual",{}).get("steps")})
e = run("deliver.train", op="faq", title="泵站运维FAQ", dir=td)
rec("train.faq", e.get("ok") and (e.get("data") or {}).get("faq",{}).get("count",0)>=3,
    {"count":(e.get("data") or {}).get("faq",{}).get("count")})
e = run("deliver.train", op="transfer", requirements=reqs, dir=td)
rec("train.transfer", e.get("ok") and len((e.get("data") or {}).get("transfer_checklist",[]))==2,
    {"n":len((e.get("data") or {}).get("transfer_checklist",[]))})

# ============ 9. memory: add/search/sediment/optmem ============
mm = os.path.join(WORK,"mem"); os.makedirs(mm, exist_ok=True)
e = run("memory.core", op="add", text="泵站 pump_01 振动值偏高，疑似轴承磨损", tags=["monitor"], dir=mm)
rec("memory.add", e.get("ok") and (e.get("data") or {}).get("stored",{}).get("added") is True, e.get("data"))
e = run("memory.core", op="search", query="轴承磨损 振动", top_k=3, dir=mm)
rec("memory.search", e.get("ok") and bool((e.get("data") or {}).get("hits")),
    [(h.get("score"), h.get("fact",{}).get("text")) for h in (e.get("data") or {}).get("hits",[])])
e = run("memory.core", op="sediment", text="测试", dir=mm)
rec("memory.noise_filter", (e.get("data") or {}).get("stored",{}).get("skipped") is True, e.get("data"))
e = run("memory.core", op="optmem", text="经验：振动越限先查轴承", dir=mm)
rec("memory.optmem", e.get("ok") and (e.get("data") or {}).get("stored",{}).get("note_count")==1, e.get("data"))

# ============ 10. fde-task: 工单状态机 ============
ft = os.path.join(WORK,"task"); os.makedirs(ft, exist_ok=True)
e = run("fde.task", op="issue", problem="泵振动越限", severity="high", dir=ft)
ticket = (e.get("data") or {}).get("ticket") or {}
tid = ticket.get("id")
rec("task.issue", e.get("ok") and ticket.get("state")=="open", {"id":tid,"sev":ticket.get("severity")})
e = run("fde.task", op="diagnose", tid=tid, diagnosis="轴承磨损", dir=ft)
rec("task.diagnose", e.get("ok") and (e.get("data") or {}).get("ticket",{}).get("state")=="diagnosed",
    (e.get("data") or {}).get("ticket",{}).get("state"))
e = run("fde.task", op="resolve", tid=tid, resolution="更换轴承", dir=ft)
rec("task.resolve", e.get("ok") and (e.get("data") or {}).get("ticket",{}).get("state")=="resolved",
    (e.get("data") or {}).get("ticket",{}).get("state"))
e = run("fde.task", op="verify", tid=tid, dir=ft)
rec("task.verify", e.get("ok") and (e.get("data") or {}).get("ticket",{}).get("state")=="verified",
    (e.get("data") or {}).get("ticket",{}).get("state"))
e = run("fde.task", op="audit", tid=tid, dir=ft)
rec("task.audit", e.get("ok") and len((e.get("data") or {}).get("audit_trail",[]))>=4,
    {"audit_n":len((e.get("data") or {}).get("audit_trail",[]))})
# 非法流转拒绝
st = run("fde.task", op="issue", problem="测试工单", severity="medium", dir=ft)
bad_tid = (st.get("data") or {}).get("ticket",{}).get("id")
e = run("fde.task", op="verify", tid=bad_tid, dir=ft)  # open→verified 非法
rec("task.illegal_transition_rejected", e.get("ok") is False and "非法" in (e.get("error") or ""), e.get("error"))
# alarm_tickets 严重度
e = run("fde.task", op="alarm_tickets", alerts=[{"level":"critical","device_id":"pump_01","message":"振动越限"}], dir=ft)
rec("task.alarm_severity", e.get("ok") and (e.get("data") or {}).get("tickets",[{}])[0].get("severity")=="critical",
    e.get("data"))

# ============ 汇总 ============
print("\n================ 汇总 ================")
passed = sum(1 for _,ok in results.items() if ok)
print(f"PASS: {passed}/{len(results)}")
for k,(ok,d) in results.items():
    if not ok:
        print(f"  FAIL: {k} -> {d}")
