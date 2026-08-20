# -*- coding: utf-8 -*-
import sys, os, time, tempfile
sys.path.insert(0, r"本仓库根目录")
from solo.memory import Memory

# 1) 性能: 3000 条 add_fact (原实现 ~73.5s)
tmp = tempfile.mkdtemp(prefix="perf_")
m = Memory(tmp)
t0 = time.time()
N = 3000
for i in range(N):
    m.add_fact(f"性能测试事实 #{i} 数据点 value={i}", tags=["perf", f"b{i%10}"])
add_t = time.time() - t0
print(f"ADD {N} 条: {add_t:.3f}s  p95={add_t/N*1000:.3f}ms/条", flush=True)

t0 = time.time()
hits = m.search("性能测试事实 #2999", top_k=3)
search_t = time.time() - t0
nf = len(m._load(m._facts_path, []))
print(f"facts.json 落盘条数(合并后): {nf}  search: {search_t:.3f}s hits={len(hits)}", flush=True)
assert add_t < 10, f"add_fact 仍过慢: {add_t}s"
assert nf == N, f"合并后条数应={N} 实际={nf}"
assert hits and any("性能测试事实" in h["text"] for h in hits)

# 2) 去重仍生效 (跨实例)
m2 = Memory(tmp)
assert m2.add_fact("性能测试事实 #2999 数据点 value=2999") is False
print("跨实例去重: OK (返回 False)", flush=True)

# 3) 语义检索 mock embed 缓存仍正确
class FakeMem(Memory):
    def _try_embed(self, text):
        return [float(len(text) % 7), float(len(text) % 5)]
m3 = FakeMem(tempfile.mkdtemp(prefix="emb_"))
m3.add_fact("本体建模用于工厂数据问答", ["本体"])
m3.add_fact("GitHub凭证已配置", ["github"])
r = m3.search("本体", top_k=2, semantic=True)
print("semantic search top1:", r[0]["text"], flush=True)
assert "本体" in r[0]["text"]

# 4) write/update/delete 落盘正确
m4 = Memory(tempfile.mkdtemp(prefix="wd_"))
assert m4.write("设备 d1 温度 90 度")["action"] == "ADD"
assert len(m4._load(m4._facts_path, [])) == 1
assert m4.write("设备 d1 温度 90 度")["action"] == "SKIP"
assert len(m4._load(m4._facts_path, [])) == 1
u = m4.update_fact("设备 d1 温度 90 度", "设备 d1 温度 95 度")
assert u["ok"] and m4._load(m4._facts_path, [])[0]["text"] == "设备 d1 温度 95 度"
d = m4.delete_fact(text="设备 d1 温度 95 度")
assert d["ok"] and len(m4._load(m4._facts_path, [])) == 0
print("write/update/delete 落盘: OK", flush=True)

# 5) P0 路径穿越: 逃逸被拒
m5 = Memory(tempfile.mkdtemp(prefix="pi_"))
escapes = ["../evil", "../../etc/passwd", "..\\..\\win.ini", "/etc/passwd",
           "C:/Windows/system32", "a/../../x", "..", ".hidden"]
rejected = 0
for evil in escapes:
    for fn in ("set_scenario", "log_session"):
        try:
            getattr(m5, fn)(evil, "content")
            print(f"!! {fn}({evil!r}) 未被拦截(严重)", flush=True)
        except (ValueError, TypeError):
            rejected += 1
print(f"路径穿越注入: {rejected}/{len(escapes)*2} 次被拒", flush=True)
escaped = []
for root, dirs, files in os.walk(tmp):
    for f in files:
        if "evil" in f or "win.ini" in f or f == "passwd":
            escaped.append(os.path.join(root, f))
print("逃逸文件:", escaped, flush=True)
assert not escaped, f"检测到文件逃逸: {escaped}"
m5.set_scenario("proj_a1", "ctx")
m5.log_session("sess_2026", "log")
print("合法 scenario/session 写入: OK", flush=True)
print("ALL MEMORY CHECKS PASSED", flush=True)
