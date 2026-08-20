import json, sys, os, tempfile
sys.path.insert(0, "本仓库根目录")
from fde_runtime.loader import AgentRuntime

rt = AgentRuntime()
rt.scan(tolerate=True)
print("REGISTRY ATOMS:", len(rt.manifests))
for m in rt.manifests:
    print("  ", m["name"], m["path"], m["capabilities"])

rt.load(tolerate=True)
print("LOADED:", len(rt.agents))
print("CAPS:", sorted(rt.capabilities().keys()))

# 主交付链（含写作步骤）
asm_path = "本仓库根目录/assemblies/fde-workflow.json"
with open(asm_path, encoding="utf-8") as f:
    asm = json.load(f)
wd = tempfile.mkdtemp(prefix="fde_link_")
res = rt.run_flow(asm, workdir=wd)
print("OK:", res["ok"])
print("loop_closed:", res.get("loop_closed"))
final = res["data"]["final"]
print("worst_level:", final["worst_level"])
print("tickets_n:", final["tickets_n"])
print("accept:", final["accept"])
print("writing_qa_passed:", final.get("writing_qa_passed"))
print("writing_evidence_pass:", final.get("writing_evidence_pass"))
for t in res["data"]["steps"]:
    st = "ok" if t["ok"] else "FAIL:" + (t.get("error") or "")[:60]
    extra = ""
    if t["id"] == "write_qa" and t["ok"]:
        extra = " issues=" + str(t["data"]["report"]["total_issues"]) + " passed=" + str(t["data"]["passed"])
    if t["id"] == "write_evidence" and t["ok"]:
        extra = " summary=" + str(t["data"]["summary"].get("verdict"))
    print(f"  {t['id']:14s} {t['capability']:18s} -> {st}{extra}")

# 写作原子独立验证
print("\n-- write-qa scan --")
print(json.dumps(rt.run_capability("write.qa", op="scan",
    text="这是一个测试通过赋能闭环实现降维打击")["data"], ensure_ascii=False)[:300])
print("-- write-evidence fact_check --")
print(json.dumps(rt.run_capability("write.evidence", op="fact_check",
    text="温度90度", source_rows=[{"temperature": 90}])["data"]["summary"], ensure_ascii=False))
