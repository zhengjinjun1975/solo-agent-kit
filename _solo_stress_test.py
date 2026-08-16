# -*- coding: utf-8 -*-
"""solo 压力 + 边界 + 路径注入实测脚本(真实数据, 非空壳)"""
import sys, os, json, time, tempfile, threading, hashlib, random
sys.path.insert(0, "E:/open-source/solo-agent-kit")
import tempfile

RESULTS = {"stress": {}, "boundary": {}, "path_injection": {}}

# ═══════════ 1) 压力: memory 大数据量 ═══════════
def stress_memory():
    tmp = tempfile.mkdtemp(prefix="solo_stress_mem_")
    from solo.memory import Memory
    m = Memory(tmp)
    t0 = time.time()
    N = 20000
    for i in range(N):
        m.add_fact(f"压力测试事实 #{i} 数据点 value={i}", tags=["stress", f"batch{i%10}"])
    add_t = time.time() - t0
    # 检索
    t0 = time.time()
    hits = m.search("压力测试事实 #19999")
    search_t = time.time() - t0
    # 画像
    t0 = time.time()
    for i in range(2000):
        m.set_profile(f"k{i}", f"v{i}")
    prof_t = time.time() - t0
    nf = len(m._load(m._facts_path, []))
    RESULTS["stress"]["memory"] = {
        "facts": N, "add_sec": round(add_t,2), "facts_stored": nf,
        "search_sec": round(search_t,2), "search_hits": len(hits),
        "profile_2000_sec": round(prof_t,2),
        "p95_per_fact_ms": round(add_t/N*1000, 3)
    }
    print(json.dumps(RESULTS["stress"]["memory"], ensure_ascii=False))

# ═══════════ 2) 压力: memory 并发写入 ═══════════
def stress_memory_concurrent():
    tmp = tempfile.mkdtemp(prefix="solo_stress_memc_")
    from solo.memory import Memory
    errors = []
    def writer(worker_id):
        try:
            m = Memory(tmp)
            for i in range(500):
                m.add_fact(f"worker{worker_id}-fact-{i}", tags=["concurrent"])
        except Exception as e:
            errors.append(f"w{worker_id}: {type(e).__name__}: {e}")
    threads = [threading.Thread(target=writer, args=(w,)) for w in range(8)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    elapsed = time.time() - t0
    # 最终一致性检查
    m = Memory(tmp)
    total = len(m._load(m._facts_path, []))
    RESULTS["stress"]["memory_concurrent"] = {
        "threads": 8, "total_writes": 8*500, "stored": total,
        "elapsed_sec": round(elapsed,2), "errors": errors[:5], "error_count": len(errors),
        "data_loss": total < 8*500
    }
    print(json.dumps(RESULTS["stress"]["memory_concurrent"], ensure_ascii=False))

# ═══════════ 3) 压力: monitor 长链(多次评估不崩/性能) ═══════════
def stress_monitor():
    import importlib
    try:
        from solo.factory.monitor import evaluate_point, monitor_snapshot
    except Exception as e:
        RESULTS["stress"]["monitor"] = {"error": f"import: {e}"}
        print(json.dumps(RESULTS["stress"]["monitor"], ensure_ascii=False)); return
    # 长链: 连续评估大量点
    t0 = time.time()
    ok = 0; err = 0
    pts = []
    for i in range(3000):
        pts.append({"key": f"KPI_{i}", "value": float(i), "spec": {"target": 100, "mode": "min"}})
    try:
        import inspect
        sig = inspect.signature(evaluate_point)
        params = list(sig.parameters.keys())
        # 用 kwargs 逐点
        for p in pts[:500]:
            try:
                if "point" in params:
                    evaluate_point(point=p)
                elif "key" in params:
                    evaluate_point(key=p["key"], value=p["value"], spec=p["spec"])
                else:
                    evaluate_point(p)
                ok += 1
            except Exception as e:
                err += 1
    except Exception as e:
        RESULTS["stress"]["monitor"] = {"error": f"run: {type(e).__name__}: {e}"}
        print(json.dumps(RESULTS["stress"]["monitor"], ensure_ascii=False)); return
    elapsed = time.time() - t0
    RESULTS["stress"]["monitor"] = {
        "evaluated": ok, "errored": err,
        "elapsed_sec": round(elapsed,2),
        "per_call_ms": round(elapsed/max(1,ok)*1000,3)
    }
    print(json.dumps(RESULTS["stress"]["monitor"], ensure_ascii=False))

# ═══════════ 4) 压力: evidence 大数据量 ═══════════
def stress_evidence():
    try:
        from solo.factory.evidence import build_ledger
    except Exception as e:
        RESULTS["stress"]["evidence"] = {"error": f"import: {e}"}
        print(json.dumps(RESULTS["stress"]["evidence"], ensure_ascii=False)); return
    big = []
    for i in range(10000):
        big.append({"claim": f"证据声明 {i}", "source": "stress.csv",
                    "status": "confirmed" if i%2 else "pending",
                    "confidence": 0.5 + (i%10)/20})
    t0 = time.time()
    try:
        import inspect
        sig = inspect.signature(build_ledger)
        params = list(sig.parameters.keys())
        r = build_ledger(big) if "rows" in params else build_ledger(evidence=big)
        elapsed = time.time() - t0
        RESULTS["stress"]["evidence"] = {"rows": len(big), "elapsed_sec": round(elapsed,2),
                                          "output_keys": list(r.keys())[:6] if isinstance(r,dict) else type(r).__name__}
    except Exception as e:
        RESULTS["stress"]["evidence"] = {"error": f"run: {type(e).__name__}: {e}"}
    print(json.dumps(RESULTS["stress"]["evidence"], ensure_ascii=False))

# ═══════════ 5) 边界: 空输入/非法/异常 ═══════════
def boundary_core():
    from solo.memory import Memory
    tmp = tempfile.mkdtemp(prefix="solo_bnd_")
    m = Memory(tmp)
    b = []
    # 空/非法记忆
    for bad in [None, "", 123, [], {}, "   "]:
        try:
            r = m.add_fact(bad)
            b.append(f"add_fact({bad!r})->{r}")
        except Exception as e:
            b.append(f"add_fact({bad!r})->{type(e).__name__}")
    try:
        r = m.search(None); b.append(f"search(None)->{type(r).__name__}")
    except Exception as e:
        b.append(f"search(None)->{type(e).__name__}")
    try:
        m.set_profile(None, None); b.append("set_profile(None,None)->ok")
    except Exception as e:
        b.append(f"set_profile(None,None)->{type(e).__name__}")

    # data_connector 边界
    from solo.data_connector import connect, DataSourceError
    for bad in [None, "", [], 0]:
        try:
            connect(bad); b.append(f"connect({bad!r})->未拦截!")
        except DataSourceError:
            b.append(f"connect({bad!r})->DataSourceError OK")
        except Exception as e:
            b.append(f"connect({bad!r})->{type(e).__name__}")
    # 不存在的文件
    for fn,args in [("connect", [{"type":"csv","path":"/nope.csv"}]), 
                    ("connect",[{"type":"sqlite","path":"/nope.db","table":"t"}])]:
        try:
            connect(*args); b.append(f"{fn}{args}->未拦截!")
        except DataSourceError:
            b.append(f"{fn}{args}->DataSourceError OK")
    RESULTS["boundary"]["core"] = b
    print(json.dumps(b, ensure_ascii=False))

# ═══════════ 6) 路径注入 ═══════════
def path_injection():
    from solo.memory import Memory
    tmp = tempfile.mkdtemp(prefix="solo_pi_")
    m = Memory(tmp)
    inj = []
    # 路径穿越: 场景名带 ../ 或绝对路径
    for evil in ["../evil", "../../etc/passwd", "..\\..\\win.ini", "/etc/passwd", "C:/Windows/system32", "a/../../x", "\x00bad"]:
        try:
            # 尝试通过 add_fact tags 或 scenario 写
            r = m.save_scenario if hasattr(m,"save_scenario") else None
            # 用 add_fact 带 tags
            m.add_fact("正常内容", tags=[evil])
            inj.append(f"tags {evil!r}: 未拦截")
        except Exception as e:
            inj.append(f"tags {evil!r}: {type(e).__name__}")
    # 检查是否有文件逃逸出 tmp
    import glob
    escaped = []
    for root,dirs,files in os.walk(os.path.expanduser("~")):
        for f in files:
            if "evil" in f or "win.ini" in f or f in ("passwd",):
                escaped.append(os.path.join(root,f))
    RESULTS["path_injection"]["tags_paths"] = inj
    RESULTS["path_injection"]["escaped_files_found"] = escaped[:5]
    print(json.dumps(inj, ensure_ascii=False))
    print("escaped:", escaped[:5])

if __name__ == "__main__":
    stress_memory()
    stress_memory_concurrent()
    stress_monitor()
    stress_evidence()
    boundary_core()
    path_injection()
    print("\n══ FULL ══")
    print(json.dumps(RESULTS, ensure_ascii=False, indent=1))
