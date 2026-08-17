# -*- coding: utf-8 -*-
"""组装链 2.0 实测：fde-workflow 全链跑通 + when/optional 条件 + final 聚合。"""
from __future__ import annotations
import os, sys, json, tempfile
ROOT = r"E:\open-source\solo-agent-kit"
sys.path.insert(0, ROOT)
from fde_runtime.loader import AgentRuntime

rt = AgentRuntime(atoms_root=os.path.join(ROOT, "atoms"),
                  registry_path=os.path.join(ROOT, "registry.json"))
rt.scan(tolerate=True); rt.load(tolerate=True)

asm_path = os.path.join(ROOT, "assemblies", "fde-workflow.json")
with open(asm_path, encoding="utf-8") as f:
    asm = json.load(f)
print("assembly:", asm["name"], asm["schema"], asm["version"])

WORK = tempfile.mkdtemp(prefix="fde_flow_")
flow = rt.run_flow(asm, workdir=WORK)
ok = flow.get("ok")
steps = flow.get("data", {}).get("steps", [])
final = flow.get("data", {}).get("final")
print("\nloop_closed:", flow.get("loop_closed"))
print("=== steps ===")
for s in steps:
    print(f"[{s.get('id')}] cap={s.get('capability')} op={s.get('op')} ok={s.get('ok')} "
          f"skipped={s.get('skipped', False)} degraded={s.get('degraded', False)}")
    if s.get("error") and not s.get("skipped"):
        print("    ERROR:", s.get("error"))
print("\n=== final ===")
print(json.dumps(final, ensure_ascii=False, indent=2)[:1200])

# ---- 断言 ----
def assert_c(cond, name, detail=""):
    print(("[PASS] " if cond else "[FAIL] ") + name + (" | " + str(detail) if detail else ""))
    return cond

ok_all = True
assert_c(flow.get("ok"), "flow.ok")
# 1. ingest 真实
ing = next(s for s in steps if s["id"]=="ingest")
assert_c(ing["ok"] and ing["data"]["ingested"]["count"]==8, "ingest.8pts", ing["data"]["ingested"]["count"])
# 2. spc 消费 ingest 的值 ($ref)
spc = next(s for s in steps if s["id"]=="spc")
assert_c(spc["ok"] and spc["data"]["spc"]["mean"] is not None, "spc.consumes_ingest",
         {"mean": spc["data"]["spc"]["mean"], "n": len(spc["data"]["spc"].get("points",[]))})
# 3. predict 消费 ingest
pred = next(s for s in steps if s["id"]=="predict")
assert_c(pred["ok"] and pred["data"]["risk"]["level"] is not None, "predict.risk",
         pred["data"]["risk"].get("level"))
# 4. decision 消费 spc (data.cap 结果)
dec = next(s for s in steps if s["id"]=="decision")
assert_c(dec["ok"] and dec["data"]["total"] is not None, "decision.consumes_spc",
         {"total": dec["data"].get("total"), "decisions_n": len(dec["data"].get("decisions",[]))})
# 5. ticket when 条件: predict.risk.level in [high,critical] -> 应执行
ticket = next(s for s in steps if s["id"]=="ticket")
assert_c(ticket["ok"] and not ticket.get("skipped"), "ticket.when_executed(risk high/critical)",
         {"risk_level": pred["data"]["risk"].get("level"), "ticket_id": ticket["data"]["ticket"].get("id")})
# 6. kb + maintain 消费 kb.hit
kb = next(s for s in steps if s["id"]=="kb")
maint = next(s for s in steps if s["id"]=="maintain")
assert_c(kb["ok"] and kb["data"].get("hit") is not None, "kb.suggest_hit", kb["data"].get("hit"))
assert_c(maint["ok"] and maint["data"]["advice"].get("from_kb") is True, "maintain.consumes_kb_hit",
         maint["data"]["advice"])
# 7. accept optional 闭源 -> 应执行 (因为可用)
acc = next(s for s in steps if s["id"]=="accept")
assert_c(acc["ok"] and not acc.get("skipped"), "accept.optional_executed",
         {"accept": acc["data"].get("accept")})
# 8. train 消费 requirements
train = next(s for s in steps if s["id"]=="train")
assert_c(train["ok"] and bool(train["data"]["manual"]["markdown"]), "train.executed",
         {"manual_sections": train["data"]["manual"].get("sections")})
# 9. final 聚合真实
assert_c(final.get("accept") is True, "final.accept_true", final.get("accept"))
assert_c(final.get("worst_level") is not None, "final.worst_level", final.get("worst_level"))
assert_c(final.get("tickets_n") >= 1, "final.tickets_n", final.get("tickets_n"))

# ============ 2. 验证 when 条件负向: 无越限数据 -> risk 低 -> ticket 应 skipped ============
asm2 = json.load(open(asm_path, encoding="utf-8"))
# 覆盖 ingest 为平稳数据 (无越限)
asm2["steps"][0]["inputs"]["points"] = [
    {"device_id":"pump_01","metric":"vibration","value":5.0,"ts":"2026-08-16T10:00:00"},
    {"device_id":"pump_01","metric":"vibration","value":5.1,"ts":"2026-08-16T10:01:00"},
    {"device_id":"pump_01","metric":"vibration","value":5.0,"ts":"2026-08-16T10:02:00"}]
flow2 = rt.run_flow(asm2, workdir=tempfile.mkdtemp(prefix="fde_flow2_"))
s2 = flow2.get("data", {}).get("steps", [])
ticket2 = next(s for s in s2 if s["id"]=="ticket")
pred2 = next(s for s in s2 if s["id"]=="predict")
print("\n=== when 负向测试 ===")
print("predict risk level:", pred2["data"]["risk"].get("level"), "| ticket skipped:", ticket2.get("skipped"))
assert_c(ticket2.get("skipped") is True, "when.negative_skips_ticket",
         {"risk": pred2["data"]["risk"].get("level"), "skip_reason": ticket2.get("error")})
# final tickets_n 应为 0
assert_c(flow2["data"]["final"].get("tickets_n") == 0, "final.tickets_n_zero_when_skipped",
         flow2["data"]["final"].get("tickets_n"))

# ============ 3. 验证 optional: 闭源原子缺失 -> 链不崩 ============
print("\n=== optional 降级测试 (删 deliver-accept) ===")
rt3 = AgentRuntime(atoms_root=os.path.join(ROOT, "atoms"),
                   registry_path=os.path.join(ROOT, "registry.json"))
rt3.scan(tolerate=True)
# 模拟删除闭源原子: 从 manifests 移除 deliver-accept 再 load
rt3.manifests = [m for m in rt3.manifests if m["name"] != "deliver-accept"]
rt3.load(tolerate=True)
print("loaded without closed:", sorted(rt3.agents.keys()))
flow3 = rt3.run_flow(asm, workdir=tempfile.mkdtemp(prefix="fde_flow3_"))
s3 = flow3.get("data", {}).get("steps", [])
acc3 = next(s for s in s3 if s["id"]=="accept")
print("flow3 ok:", flow3.get("ok"), "| accept skipped:", acc3.get("skipped"), "| error:", acc3.get("error"))
assert_c(acc3.get("skipped") is True and acc3.get("degraded") is True, "optional.degrades_when_closed_missing",
         {"error": acc3.get("error")})
# 后续 train 仍执行
train3 = next(s for s in s3 if s["id"]=="train")
assert_c(train3["ok"], "train.still_runs_after_optional_skip")
print("loop_closed (closed missing):", flow3.get("loop_closed"))
