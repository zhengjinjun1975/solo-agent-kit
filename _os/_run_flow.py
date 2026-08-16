import json, sys, os, tempfile
sys.path.insert(0, "E:/open-source/solo-agent-kit")
from fde_runtime.loader import AgentRuntime

rt = AgentRuntime()
rt.scan(tolerate=True)
# regenerate registry so diagnose-kb gets registered
rt.write_registry()
print("REGISTRY ATOMS:", len(rt.manifests))
for m in rt.manifests:
    print("  ", m["name"], m["path"], m["capabilities"])

rt.load(tolerate=True)
print("LOADED:", len(rt.agents))
print("CAPS:", sorted(rt.capabilities().keys()))

asm_path = "E:/open-source/solo-agent-kit/assemblies/solo-linkage-workflow.json"
with open(asm_path, encoding="utf-8") as f:
    asm = json.load(f)
wd = tempfile.mkdtemp(prefix="fde_link_")
res = rt.run_flow(asm, workdir=wd)
print("OK:", res["ok"])
print("loop_closed:", res.get("loop_closed"))
final = res["data"]["final"]
print("worst_level:", final["worst_level"])
print("tickets:", len(final["tickets"]))
print("accept:", final["accept"])
print("report keys:", list((final["report"] or {}).keys())[:6])
for t in res["data"]["steps"]:
    st = "ok" if t["ok"] else "FAIL:" + (t.get("error") or "")[:60]
    extra = ""
    if t["id"] == "anomaly" and t["ok"]:
        extra = " sudden_anomaly=" + str(t["data"].get("anomaly"))
    if t["id"] == "predict" and t["ok"]:
        extra = " rul=" + str(t["data"].get("rul"))
    if t["id"] == "adaptive" and t["ok"]:
        extra = " thr=" + str(t["data"].get("threshold", {}).get("upper"))
    if t["id"] == "evaluate" and t["ok"]:
        extra = " alarms=" + str(t["data"].get("alarms"))
    if t["id"] == "cognition" and t["ok"]:
        extra = " source=" + str(t["data"].get("source")) + " ans=" + str((t["data"].get("answer") or "")[:25])
    if t["id"] == "decision" and t["ok"]:
        extra = " decision=" + str(t["data"].get("decision")) + " actions=" + str(t["data"].get("actions", []))[:60]
    if t["id"] == "diagnose" and t["ok"]:
        extra = " hit=" + str(t["data"].get("hit")) + " cause=" + str((t["data"].get("diagnosis") or {}).get("cause"))
    if t["id"] == "package" and t["ok"]:
        pkg = t["data"].get("package") or {}
        extra = " files=" + str(len(pkg.get("files") or [])) + " accept=" + str(pkg.get("acceptance", {}).get("all_pass"))
    print(f"  {t['id']:10s} {t['capability']:18s} -> {st}{extra}")
