# -*- coding: utf-8 -*-
"""端到端7环节闭环实测脚本 - solo-agent-kit"""
import json, os, sys, tempfile, subprocess, csv

REPO = "E:/open-source/solo-agent-kit"
VALVE = os.path.join(REPO, "examples", "valve_demo_full.csv")
VALVE_SMALL = os.path.join(REPO, "examples", "valve_demo.csv")
TMP = tempfile.mkdtemp(prefix="solo_e2e_")
os.environ["SOLO_SURVEY_DIR"] = os.path.join(TMP, "surveys")
os.environ["SOLO_TICKET_DIR"] = os.path.join(TMP, "tickets")
sys.path.insert(0, REPO)

ok = fail = 0
def check(cond, msg):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {msg}")
    else: fail += 1; print(f"  FAIL  {msg}")

def cli(*args):
    r = subprocess.run([sys.executable, "-m", "solo.cli", *args],
                       capture_output=True, text=True, cwd=REPO, encoding="utf-8")
    out = r.stdout.strip()
    try: return json.loads(out)
    except Exception: return {"_raw": out, "_rc": r.returncode, "_err": r.stderr.strip()[-300:]}

print("="*70)
print("【环节1】报价 quote — 数据驱动人天估算 + 报价单")
print("="*70)
from solo.factory import quote as Q
rows = list(csv.DictReader(open(VALVE, encoding="utf-8-sig")))
eff = Q.estimate_effort(rows=rows, requirements=[{"id":"R-001"},{"id":"R-002"}], complexity="medium")
check(eff["rows"]==10, f"人天估算 rows=10 (实际{eff['rows']})")
check(eff["requirements"]==2, "需求数计入")
check(eff["total_days"]>0, f"总人天={eff['total_days']}")
quote = Q.build_quote("阀门厂智能运维", "阀本体台账+补货决策", effort=eff)
check(quote["totals"]["total"]>0, f"报价总额={quote['totals']['total']}")
check(len(quote["lines"])>=2, f"明细行数={len(quote['lines'])}")
check(quote["terms"]["交付"]=="数据交付 + 方案文档 + 现场培训 + 运维知识库", "报价条款含交付闭环")
qscore = Q.quality_score(rows)
check(0<=qscore<=1, f"数据质量分={qscore}")
# 报价与需求条数联动(来自survey, 见环节2)
print()

print("="*70)
print("【环节2】需求 survey — 访谈提纲 → 结构化 → SRS")
print("="*70)
from solo.factory import survey as S
outline = S.interview_outline("阀门制造")
check(outline["kb"]=="valve", f"行业联动 kb=valve (实际{outline['kb']})")
check(len(outline["questions"])>=5, "访谈提纲≥5题")
survey = S.Survey("阀门运维项目")
r1 = survey.collect("阀门库存盘点耗时, 补货不及时", category="生产", priority="P1",
                    acceptance=["对账成功率≥99%", "补货及时率≥95%"])
check(r1["id"]=="R-001", f"需求编号 R-001 (实际{r1['id']})")
r2 = survey.collect("设备故障无法预警", category="运维", priority="P0",
                    acceptance=["故障预警响应<5分钟"])
check(r2["id"]=="R-002", "第二需求编号 R-002")
check(len(survey.requirements)==2, "需求条目=2")
srs = survey.to_srs()
check("## 需求清单" in srs["markdown"], "SRS生成")
check("R-001" in srs["markdown"] and "R-002" in srs["markdown"], "SRS含全部需求")
# 报价输入需求条数 = survey 的 requirements (环节1↔2衔接)
eff2 = Q.estimate_effort(rows=rows, requirements=survey.requirements, complexity="medium")
check(eff2["requirements"]==2, f"报价复用survey需求数={eff2['requirements']}")
print()

print("="*70)
print("【环节3】数据 data — 清洗 → 统计 → 报告")
print("="*70)
from solo.factory import data as D
from solo import app as APP
rows = list(csv.DictReader(open(VALVE, encoding="utf-8-sig")))
clean = APP.data_clean(rows)
check(clean["output"]==9, f"数据清洗 output=9 (IQR剔除1异常值, 实际{clean['output']})")
stats = APP.data_stats(rows)
check("describe" in stats, f"数据分析列={stats.get('column')}")
check(stats["describe"].get("mean") is not None, "均值计算")
report = APP.data_report(rows)
check(report["total_rows"]==10, f"数据报告 total_rows=10")
check(report["total_cols"]>=5, f"列数={report['total_cols']}")
# 环节3→环节4衔接: 清洗后数据送本体建模
print()

print("="*70)
print("【环节4】交付 ontology/decisions — 本体建模 + 聚合问答 + 决策")
print("="*70)
from solo.factory import ontology as O
o = O.Ontology()
o.from_rows(rows, entity_name="阀门", id_col="id")
o.build()
check(len(o.entities)>=1, f"本体实体={list(o.entities.keys())}")
check(len(o.triples)>0, f"三元组={len(o.triples)}")
# 聚合问答: 计数/极值/枚举
n = o.answer("有多少台阀门")
check(len(n)>0, f"计数问答={n}")
mx = o.answer("功率最大的阀门")
check(len(mx)>0 and str(mx[0].get("value",""))=="9.0", f"极值问答值=9.0 (V007)")
enum = o.answer("状态有哪些")
check(len(enum)>0 and "在用" in enum[0]["values"], f"枚举问答(全局映射)={enum[0].get('values')}")
# 行业化列名问答（闭环 draft_questions, 需注入行业 col_cn）
o2 = O.Ontology(col_cn={"valve_type":"阀门类型","nominal_dn":"公称通径",
                    "pressure_rating":"公称压力","material":"材质"})
o2.from_rows(rows, entity_name="阀门", id_col="id"); o2.build()
vt = o2.answer("阀门类型有哪些")
check(len(vt)>0 and "球阀" in vt[0]["values"], f"行业化枚举(阀门类型)可答={vt[0].get('values')}")
dn = o2.answer("公称通径最小的阀门")
check(len(dn)>0 and str(dn[0].get("value",""))=="25", f"行业化极值(公称通径)可答={dn[0].get('value')}")
# 决策: 用 decisions 规则(需匹配表名)。这里构造库存表
from solo.factory import decisions as DEC
inv_rows = [
    {"product_id":"P1","stock":5,"safety_stock":14,"lead_time_days":7},
    {"product_id":"P2","stock":50,"safety_stock":14,"lead_time_days":7},
]
sales_rows = [{"product_id":"P1","qty":3,"date":"2024-01-01"},{"product_id":"P1","qty":4,"date":"2024-01-02"}]
dec = DEC.run_decisions({"inventory":inv_rows,"sales":sales_rows})
check(dec["total"]>=1, f"决策行动={dec['total']}")
check(any(d["entity"]=="P1" and d["action"]=="补货" for d in dec["decisions"]), "补货决策P1命中")
print()

print("="*70)
print("【环节5】验收 survey-acceptance — 验收清单 + 勾稽防漏")
print("="*70)
items = survey.prepare_acceptance()
check(len(items)==3, f"验收条目=3 (需求2条→3条可验收条款, 实际{len(items)})")
chk = survey.check()
check(chk["ok"] is True, f"勾稽ok={chk['ok']} missing={chk['missing']} orphan={chk['orphan']}")
# 记录验收结果
for a in items:
    survey.record_result(a["aid"], "通过", "实测已验证")
chk2 = survey.check()
check(chk2["stats"]["passed"]==3, f"验收通过={chk2['stats']['passed']}")
sign = survey.signoff()
check(sign["ok"] is True, f"签收ok={sign['ok']}")
print()

print("="*70)
print("【环节6】运维 support/ops — 工单 + 知识库 + 监控")
print("="*70)
from solo.factory import support as SU
st = SU.SupportTicket(dir=os.path.join(TMP,"tickets"))
tk = st.new("设备V004 CPU占用过高", severity="high")
check(tk.get("problem") is not None, f"新建工单={tk.get('id')}")
tid = tk.get("id")
pr = st.process(tid, "检查进程并重启服务")
check(pr.get("state")=="处理中", f"工单处理中={pr.get('state')}")
rs = st.resolve(tid, "清理僵尸进程, 重启agent")
check(rs.get("state")=="已解决", f"工单已解决={rs.get('state')}")
kb = SU.KnowledgeBase(dir=os.path.join(TMP,"tickets","kb"))
hits = kb.search("CPU占用高")
check(len(hits)>=1, f"知识库检索到解决方案={len(hits)}")
# ops 监控
from solo.factory import ops as OPS
mon = OPS.system_stats()
check("cpu" in mon and "memory" in mon, "本机监控结构完整")
print()

print("="*70)
print("【环节7】培训 train — 操作手册 + FAQ")
print("="*70)
from solo.factory import train as T
man = T.manual(requirements=survey.requirements, title="阀门智能运维系统操作手册")
check(man["sections"]>=1, f"手册功能模块={man['sections']}")
check(man["steps"]>0, f"操作步骤数={man['steps']}")
check("R-001" in man["markdown"] or "R-002" in man["markdown"], "手册含需求使用场景(survey衔接)")
faq = T.faq()
check(faq["count"]>=3, f"FAQ条数={faq['count']}")
# 培训与报价交付条款衔接: quote terms承诺"现场培训"已由train能力落地
print()

print("="*70)
print("【断链确认】CLI入口真实可用")
print("="*70)
r = cli("survey-structure", "阀门运维项目CLI", "阀门泄漏导致停机损失", "--priority", "P0",
        "--acceptance", "泄漏率<0.1%")
check(r.get("id")=="R-001", f"CLI survey-structure → {r.get('id')}")
r = cli("survey-acceptance", "阀门运维项目CLI")
check(r.get("count",0)>=1, f"CLI survey-acceptance → {r.get('count')}条")
r = cli("onto-answer", VALVE_SMALL, "有多少个阀门", "--industry", "阀门制造")
check(r.get("answers") and len(r.get("answers",[]))>0, f"CLI onto-answer 计数 → {r.get('answers')}")
r = cli("onto-answer", VALVE_SMALL, "公称通径最小的阀门", "--industry", "阀门制造")
check(r.get("answers") and len(r.get("answers",[]))>0, f"CLI onto-answer 极值 → {r.get('answers')}")
r = cli("onto-answer", VALVE_SMALL, "阀门类型有哪些", "--industry", "阀门制造")
check(r.get("answers") and len(r.get("answers",[]))>0, f"CLI onto-answer 枚举 → {r.get('answers')}")
r = cli("onto-to-nt", VALVE_SMALL)
check(r.get("triples",0)>0, f"CLI onto-to-nt triples={r.get('triples')}")
r = cli("onto-search", VALVE_SMALL, "阀门")
check("hits" in r, f"CLI onto-search hits={r.get('hits')}")
r = cli("draft-questions", VALVE_SMALL, "--industry", "阀门制造")
check(r.get("count",0)>=3, f"CLI draft-questions 问题集={r.get('count')}")
r = cli("lexicon-draft", VALVE_SMALL, "--industry", "阀门制造")
check(r.get("columns",0)>=5, f"CLI lexicon-draft 词典列={r.get('columns')}")
r = cli("to-factory-lexicon", VALVE_SMALL, "--industry", "阀门制造")
check("entity_cn2en" in r, "CLI to-factory-lexicon 契约生成")
r = cli("to-review-items", VALVE_SMALL, "--industry", "阀门制造")
items = r.get("items", r) if isinstance(r, dict) else r
check(isinstance(items, list) and len(items)>=1, f"CLI to-review-items 待确认队列={len(items)}")
r = cli("industry-list")
check(r.get("count",0)>=3, f"CLI industry-list 行业数={r.get('count')}")
r = cli("industry-current")
check("current" in r, f"CLI industry-current = {r.get('current')}")
r = cli("report-draft", "--industry", "阀门制造", "--hit", "0.8", "--questions", "20", "--hits", "16")
check("report" in r, "CLI report-draft 交付报告")
r = cli("industry-set", "阀门制造", VALVE_SMALL, "--out-dir", os.path.join(TMP,"ind"))
check(isinstance(r, dict) and "industry" in r, f"CLI industry-set 改行业联动 → {r}")
print()

print("="*70)
print(f"汇总: PASS={ok} FAIL={fail}")
print("="*70)
# 恢复全局行业状态，避免污染其他测试/用户会话（industry-set 会持久化当前行业）
try:
    from solo.factory import industry as ind_restore
    ind_restore.set_current_industry(None)
    print("已复位当前行业状态 →", ind_restore.get_current_industry())
except Exception as e:  # noqa: BLE001
    print("行业状态复位失败:", e)
