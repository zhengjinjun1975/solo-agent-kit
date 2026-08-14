# -*- coding: utf-8 -*-
"""survey.py — 需求→验收生命周期（需求调研 → 结构化需求 → SRS → 验收清单/签收）。

单一概念域：把一次业务需求的"采集→结构化→文档→验收"走完整条链，
并保证**单一事实来源**——每条需求编号(R-xxx)与它的验收条目(A-xxx)勾稽对齐，
验收阶段自动防漏项（有需求没验收 / 有验收没需求都报出来）。

数据驱动：
- 访谈提纲按行业从 config/industries.json 联动（实体/量词/说明 → 行业化提问）
- 需求编号 R-001.. 与验收编号 A-001.. 由单一计数器派生（确定性）

复用（极简，不重造）：
- industry.load_industry / industries_list  行业联动（访谈提纲行业化）
- assist._industry_ctx                       行业上下文（实体/量词/列名）
- writing.scan / ai_taste                     SRS 生成后做中文质量自检
- task.Task                                   生命周期阶段状态机（采集/结构化/SRS/验收）
- plugins.excel_report.acceptance_report      验收清单出 xlsx（签收单）

零额外依赖，纯标准库（xlsx 仅在调用导出时依赖 openpyxl）。
"""
from __future__ import annotations

import datetime
import json
import os
import re

from .industry import load_industry, industries_list, apply_industry
from .assist import _industry_ctx

# ═══ 领域常量（确定性优先：枚举提前钉死，防乱填）═══
CATEGORIES = ("生产", "销售", "运维", "管理")   # 需求分类
PRIORITIES = ("P0", "P1", "P2")                # 优先级
PHASES = ("采集", "结构化", "SRS", "验收")      # 生命周期阶段（对应 task 状态）

_DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".solo", "surveys")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ═══════════════════════════ 1. 需求采集：访谈提纲（行业数据驱动）═══════════════════════════
def interview_outline(industry: str = None) -> dict:
    """返回某行业的访谈提纲模板。

    数据驱动：从 industries.json 联动该行业的 实体/量词/说明，
    生成带行业语义的提问提纲（比起通用模板更贴合现场）。
    industry 为空 → 跟随"当前行业"（load_industry 已内置联动）。

    返回 {"industry", "kb", "entity_cn", "measure", "note", "questions"}。
    """
    ctx = _industry_ctx(industry)
    cfg = load_industry(industry)
    ent = ctx["entity_cn"]
    measure = ctx["measure"]
    base = [
        "现状：目前业务怎么运转？最费人/最易错的一环在哪？",
        f"对象：请列举核心{ent}（{measure}计）及其关键属性，哪些字段是关键？",
        "痛点：现阶段最头疼的问题是什么？多久发生一次、影响多大？",
        "期望：最想先解决的 1~3 件事是什么？做成什么样算'好'？",
        "约束：有无预算/工期/数据/合规限制？新方案要接什么系统？",
        "边界：哪些明确不做？责任界面如何划分？",
    ]
    questions = base[:]
    # 行业化追问：从行业 note / 实体名落一条更贴现场的题
    note = (cfg.get("note") or "").strip()
    questions.append(
        f"行业(={ctx['kb']})：围绕{ent}（{measure}），针对{'、'.join((note or '行业要点'))}"
        f"，现有管控/流程有哪些缺口？")
    return {"industry": apply_industry(industry)["industry"], "kb": ctx["kb"],
            "entity_cn": ent, "measure": measure, "note": note,
            "questions": questions}


def industries() -> list:
    """列出已登记行业（供访谈提纲选行业）。复用 industry.industries_list。"""
    return industries_list()


# ═══════════════════════════ 2. 需求结构化：录入 + 编号 + 分类 + 可验收条款 ═══════════════════════════
def _require_category(cat: str) -> str:
    cat = (cat or "").strip()
    if cat not in CATEGORIES:
        raise ValueError(f"分类需为 {CATEGORIES} 之一，收到: {cat!r}")
    return cat


def _require_priority(pr: str) -> str:
    pr = (pr or "").strip().upper()
    if pr not in PRIORITIES:
        raise ValueError(f"优先级需为 {PRIORITIES} 之一，收到: {pr!r}")
    return pr


def structure_requirement(story: str, category: str = "生产", priority: str = "P2",
                          acceptance: list = None, title: str = None) -> dict:
    """把一条用户故事/痛点结构化为需求条目。

    - 校验分类/优先级（确定性优先：非法值直接报错，不静默兜底）
    - 自动派生需求标题（未给 title 时取自 story 摘要）
    - 可验收条款 acceptance：不传则从 story 抽取"动词+对象"作为占位验收项
    - 编号 R-xxx 由调用方（Survey.collect）统一分配，保证单一事实来源

    返回 {"id"(占位), "title", "story", "category", "priority", "acceptance"}。
    """
    cat = _require_category(category)
    pr = _require_priority(priority)
    story = (story or "").strip()
    if not story:
        raise ValueError("story（用户故事/痛点）不能为空")
    acc = list(acceptance) if acceptance else _auto_acceptance(story)
    return {
        "id": "",  # 由 Survey 分配
        "title": (title or story[:24]).strip(),
        "story": story,
        "category": cat,
        "priority": pr,
        "acceptance": acc,
    }


def _auto_acceptance(story: str) -> list:
    """从故事抽取动词短语生成占位可验收条款（如没有显式提供）。"""
    m = re.search(r"([\u4e00-\u9fff]{2,8}(?:率|量|度|数|额))|(提升|降低|减少|增加|支持|实现|提供)[\u4e00-\u9fff]{0,10}",
                  story)
    if m:
        return [f"验证{m.group(0)}可按预期观测"]
    return ["验证需求在主流程中可完整走通"]


# ═══════════════════════════ 3. SRS 生成（复用 writing 质量自检）═══════════════════════════
def generate_srs(requirements: list, title: str = "需求规格说明书") -> dict:
    """结构化需求 → 需求文档（markdown）。

    复用 writing 中文质量检查：生成后跑 scan + ai_taste，
    返回 {"markdown", "scan", "ai"}，便于上游决定是否改写/打磨。
    """
    reqs = [r for r in requirements if r.get("id")]
    md_lines = [
        f"# {title}",
        "",
        f"- 生成时间：{_now()}",
        f"- 需求条目：{len(reqs)} 条（单一事实来源，编号唯一）",
        "",
        "## 需求清单",
        "",
    ]
    for r in reqs:
        md_lines += [
            f"### {r['id']} {r['title']}",
            f"- 分类：{r['category']}　优先级：{r['priority']}",
            f"- 用户故事/痛点：{r['story']}",
            "- 可验收条款：",
        ]
        for a in r.get("acceptance", []):
            md_lines.append(f"  - {a}")
        md_lines.append("")
    md = "\n".join(md_lines).rstrip() + "\n"
    scan = ai = None
    try:
        from solo import writing as _w  # noqa: PLC0415
        scan = _w.scan(md)
        ai = _w.ai_taste(md, style="report")
    except Exception:  # noqa: BLE001
        scan = ai = {"ok": False, "note": "writing 未接入"}
    return {"markdown": md, "scan": scan, "ai": ai}


# ═══════════════════════════ 4. 验收清单：编号 → 条目 → 结果/证据 → 勾稽 ═══════════════════════════
def build_acceptance(requirements: list) -> list:
    """从结构化需求派生验收清单。

    单一事实来源勾稽：需求 R-xxx 的每条可验收条款 → 一条验收条目 A-xxx。
    返回 [{aid, rid, title, clause, result, evidence}]，result 初始 "待验收"。
    """
    out = []
    for r in requirements:
        rid = r.get("id", "")
        for clause in r.get("acceptance", []):
            out.append({
                "aid": "",  # 由 Survey 统一分配
                "rid": rid,
                "title": r.get("title", ""),
                "clause": clause,
                "result": "待验收",       # 待验收 / 通过 / 未通过
                "evidence": "",
            })
    return out


def reconcile(requirements: list, acceptance: list) -> dict:
    """勾稽：防漏项。校验需求与验收条目双向对齐。

    返回 {"ok", "missing", "orphan", "stats"}：
      - missing: 有需求但无任何验收条目的需求编号（漏验收）
      - orphan:  有验收条目但对应需求不存在的 rid（孤儿，防串台）
      - stats:   {requirements, items, passed, failed, pending}
    """
    req_ids = {r.get("id") for r in requirements if r.get("id")}
    item_req = {a.get("rid") for a in acceptance}
    missing = sorted(req_ids - item_req)                     # 需求无验收
    orphan = sorted(item_req - req_ids)                      # 验收无需求
    results = {}
    for a in acceptance:
        results[a.get("result")] = results.get(a.get("result"), 0) + 1
    return {
        "ok": not missing and not orphan,
        "missing": missing,
        "orphan": orphan,
        "stats": {
            "requirements": len(req_ids),
            "items": len(acceptance),
            "passed": results.get("通过", 0),
            "failed": results.get("未通过", 0),
            "pending": results.get("待验收", 0),
        },
    }


# ═══════════════════════════ Survey：生命周期编排（复用 task 状态机 + excel 导出）═══════════════════════════
class Survey:
    """一次需求调研的生命周期对象。

    - 阶段状态机：采集→结构化→SRS→验收（复用 task.Task.set_state 记录事件）
    - 需求与验收条目编号由同一计数器派生，勾稽单一事实来源
    - 数据持久化到 ~/.solo/surveys/<name>.json（关机不丢）
    """

    def __init__(self, name: str, industry: str = None, dir: str = None):
        self.name = name
        self.dir = dir or _DEFAULT_DIR
        os.makedirs(self.dir, exist_ok=True)
        self._path = os.path.join(self.dir, _safe(name) + ".json")
        self._task = _task_for(name, self.dir)
        self.industry = industry
        self._req_counter = 0      # 需求编号分配器
        self._acc_counter = 0      # 验收编号分配器
        self.requirements = []
        self.acceptance = []
        self._load()

    # ── 生命周期阶段（复用 task 状态机）──
    @property
    def phase(self) -> str:
        t = self._task.status(_safe(self.name))
        return t.get("state", "采集") if isinstance(t, dict) else "采集"

    def set_phase(self, phase: str) -> str:
        """推进生命周期阶段（写入 task 状态机 + 本地 JSON）。非法阶段报错。"""
        if phase not in PHASES:
            raise ValueError(f"阶段需为 {PHASES} 之一，收到: {phase!r}")
        self._task.set_state(_safe(self.name), phase)
        self._save()
        return phase

    # ── 需求采集/结构化 ──
    def collect(self, story: str, category: str = "生产", priority: str = "P2",
                acceptance: list = None, title: str = None) -> dict:
        """录入一条需求并结构化，分配唯一编号 R-xxx。返回需求条目。"""
        req = structure_requirement(story, category=category, priority=priority,
                                    acceptance=acceptance, title=title)
        self._req_counter += 1
        req["id"] = f"R-{self._req_counter:03d}"
        self.requirements.append(req)
        self.set_phase("结构化")
        return req

    def to_srs(self, title: str = None) -> dict:
        """生成 SRS 文档，推进到 SRS 阶段。"""
        self.set_phase("SRS")
        return generate_srs(self.requirements, title=title or f"{self.name}需求规格说明书")

    # ── 验收 ──
    def prepare_acceptance(self) -> list:
        """从需求派生验收清单并分配 A-xxx 编号。重复调用重建（防漏项）。"""
        self.set_phase("验收")
        self._acc_counter = 0
        self.acceptance = []
        for a in build_acceptance(self.requirements):
            self._acc_counter += 1
            a["aid"] = f"A-{self._acc_counter:03d}"
            self.acceptance.append(a)
        self._save()
        return self.acceptance

    def record_result(self, aid: str, result: str, evidence: str = "") -> dict:
        """记录某验收条目结果/证据。result: 通过/未通过/待验收。"""
        if result not in ("通过", "未通过", "待验收"):
            raise ValueError(f"验收结果需为 通过/未通过/待验收，收到: {result!r}")
        for a in self.acceptance:
            if a["aid"] == aid:
                a["result"] = result
                a["evidence"] = evidence
                self._save()
                return a
        raise KeyError(f"验收条目 {aid} 不存在")

    def check(self) -> dict:
        """勾稽：防漏项检查（需求↔验收双向对齐）。"""
        return reconcile(self.requirements, self.acceptance)

    def signoff(self, inspector: str = "", path: str = None) -> dict:
        """签收单：勾稽汇总 + 导出 xlsx（复用 excel_report）。

        返回 {"ok", "check", "excel", "summary"}；ok 表示无漏项。
        """
        if self.phase != "验收":
            self.prepare_acceptance()
        chk = self.check()
        xlsx = {}
        try:
            from solo.plugins import excel_report  # noqa: PLC0415
            xlsx = excel_report.acceptance_report(
                self.acceptance, title=f"{self.name}验收签收单", path=path)
        except Exception as e:  # noqa: BLE001
            xlsx = {"ok": False, "error": str(e)}
        return {
            "ok": chk["ok"],
            "check": chk,
            "excel": xlsx,
            "summary": {
                "name": self.name,
                "industry": self.industry,
                "inspector": inspector,
                "signed_at": _now(),
                **chk["stats"],
            },
        }

    # ── 持久化 ──
    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    d = json.load(f)
                self.industry = d.get("industry")
                self.requirements = d.get("requirements", [])
                self.acceptance = d.get("acceptance", [])
                self._req_counter = d.get("req_counter", len(self.requirements))
                self._acc_counter = d.get("acc_counter", len(self.acceptance))
                if d.get("phase"):
                    self.set_phase(d["phase"])
            except (OSError, json.JSONDecodeError):
                pass

    def _save(self):
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump({"name": self.name, "industry": self.industry,
                           "phase": self.phase, "req_counter": self._req_counter,
                           "acc_counter": self._acc_counter,
                           "requirements": self.requirements,
                           "acceptance": self.acceptance},
                          f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def _safe(name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name.strip())[:40] or "survey"


def _task_for(name: str, survey_dir: str):
    """为调研建一个 task 状态机（复用 task.Task，阶段=状态），隔离到调研目录。"""
    from solo import task as _task_mod  # noqa: PLC0415
    tdir = os.path.join(survey_dir, ".tasks")
    t = _task_mod.Task(tdir)
    if "error" in t.status(_safe(name)):
        t.new(name, tid=_safe(name))
    return t
