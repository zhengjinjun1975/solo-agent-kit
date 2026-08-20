# -*- coding: utf-8 -*-
"""linkage.py — 三大开源生态联动（跨仓库能力复用）适配层。

solo FDE 原子化重构后，与另外两个开源仓库形成「开源原子联动」：
  - factory-ontology-kit  → 认知原子（factory-cognition：本体问答 / 离线 RAG 知识检索）
  - sme-decision-ontology → 决策原子（sme-decision：决策 / 阈值回灌 / 行动清单）

边界铁律（对齐方案 §3.6）：**算法开源、数据不出厂**。
  - 联动的是算法/能力（open-source 原子），不共享甲方数据；
  - 各仓库数据各自落在本地 data/，联动只传「算法入参」（如路径/问题/入参），
    不把一份工厂数据复制到另一仓库；
  - 本层只做「发现兄弟仓库 + 把其 codes/ 加入 import 路径」，不做任何编排/交付增值
    （编排/增值归闭源层，开源原子禁依赖闭源原子，见 loader.check_open_source_boundary）。

发现策略（按优先级）：
  1. 环境变量：FACTORY_ONTOLOGY_KIT_DIR / SME_DECISION_ONTOLOGY_DIR
  2. 兄弟仓库相对路径（solo-agent-kit 的同级目录 ../factory-ontology-kit 等）
  3. 未找到 → present=False，调用方降级（不阻断），保证 solo 独立可跑。
纯标准库，零第三方依赖。
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # solo-agent-kit/
_OS_ROOT = os.path.dirname(_REPO_ROOT)  # 上级目录


def _norm(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p or ""))


def find_factory() -> str | None:
    """定位 factory-ontology-kit 仓库根目录，未找到返回 None。"""
    cands = [
        os.environ.get("FACTORY_ONTOLOGY_KIT_DIR"),
        os.path.join(_OS_ROOT, "factory-ontology-kit"),
        os.path.join(os.path.dirname(_REPO_ROOT), "factory-ontology-kit"),
    ]
    for c in cands:
        if not c:
            continue
        root = _norm(c)
        if os.path.isdir(os.path.join(root, "codes")) and \
           os.path.exists(os.path.join(root, "codes", "ontology_qa_v3.py")):
            return root
    return None


def find_sme() -> str | None:
    """定位 sme-decision-ontology 仓库根目录，未找到返回 None。"""
    cands = [
        os.environ.get("SME_DECISION_ONTOLOGY_DIR"),
        os.path.join(_OS_ROOT, "sme-decision-ontology"),
        os.path.join(os.path.dirname(_REPO_ROOT), "sme-decision-ontology"),
    ]
    for c in cands:
        if not c:
            continue
        root = _norm(c)
        if os.path.isdir(os.path.join(root, "codes")) and \
           os.path.exists(os.path.join(root, "codes", "rules_engine.py")):
            return root
    return None


def add_codes_to_path(repo_root: str | None, sub: str = "codes") -> bool:
    """把仓库 codes/ 目录加入 sys.path，返回是否成功。"""
    if not repo_root:
        return False
    p = os.path.join(repo_root, sub)
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
    return os.path.isdir(p)


def _repo_codes_dirs() -> set:
    """所有已发现兄弟仓库的 codes 绝对路径（用于跨仓库隔离）。"""
    dirs = set()
    for fn in (find_factory, find_sme):
        root = fn()
        if root:
            dirs.add(os.path.normpath(os.path.join(root, "codes")))
    return dirs


from contextlib import contextmanager  # noqa: E402


@contextmanager
def codes_isolation(repo_root: str | None):
    """在指定仓库 codes/ 下运行，隔离顶层模块名冲突（如双方共用 core）。

    两个兄弟仓库都在 codes/ 下定义了顶层包 `core`（factory 为常规包、sme 为命名空间包），
    直接把两份 codes 同时放进 sys.path 会让 `import core` 命中先导入的那份而冲突（
    `from core.domain_model import ...` 报 No module named）。本隔离器：
      1) 把目标 codes 置于 sys.path 首位；
      2) 临时移除其它兄弟仓库的 codes，避免 namespace `core` 被工厂常规包抢占；
      3) 清掉 `core`（及其子模块）的已导入缓存，使 `from core...` 精确命中目标仓库；
    运行后恢复 sys.path 与模块缓存。纯标准库，跨仓库联动健壮性兜底。
    """
    if not repo_root:
        yield None
        return
    codes = os.path.normpath(os.path.join(repo_root, "codes"))
    if not os.path.isdir(codes):
        yield None
        return
    others = _repo_codes_dirs() - {codes}
    saved_path = list(sys.path)
    for p in list(sys.path):
        np = os.path.normpath(p) if p else p
        if np in others or np == codes:
            sys.path.remove(p)
    saved_mods = {k: sys.modules[k] for k in list(sys.modules)
                  if k == "core" or k.startswith("core.")}
    for k in saved_mods:
        del sys.modules[k]
    sys.path.insert(0, codes)
    try:
        yield codes
    finally:
        sys.path[:] = saved_path
        sys.modules.update(saved_mods)


def factory_codes_path() -> str | None:
    root = find_factory()
    if not root:
        return None
    add_codes_to_path(root)
    return os.path.join(root, "codes")


def sme_codes_path() -> str | None:
    root = find_sme()
    if not root:
        return None
    add_codes_to_path(root)
    return os.path.join(root, "codes")


def status() -> dict:
    """联动状态自省（供 linkage op 与测试断言）。"""
    f = find_factory()
    s = find_sme()
    return {
        "factory_ontology_kit": {
            "present": f is not None,
            "dir": f,
            "role": "认知原子：本体问答 / 离线RAG知识检索",
            **(_repo_deps(f) or {}),
        },
        "sme_decision_ontology": {
            "present": s is not None,
            "dir": s,
            "role": "决策原子：决策 / 阈值回灌 / 行动清单",
            **(_repo_deps(s) or {}),
        },
        "boundary": "算法开源联动，数据不出厂（各库数据本地自持，仅传算法入参）",
    }


# ═══════════════════════════════════════════════════════════════════
# P1：跨开源强联动健壮 —— 依赖库版本检测 / 缺失清晰报错 / 回退
# ═══════════════════════════════════════════════════════════════════
_REQUIRED_LIBS = {
    "factory-ontology-kit": {
        "codes/ontology_qa_v3.py": "本体问答核心(算法开源)",
        "codes/bm25_retrieval.py": "离线检索(BM25,纯标准库)",
    },
    "sme-decision-ontology": {
        "codes/rules_engine.py": "决策规则引擎(纯标准库)",
        "codes/feedback_engine.py": "反馈回灌引擎",
    },
}


def _repo_deps(repo_root: str | None) -> dict:
    """返回某兄弟仓库的关键依赖文件在位情况：{deps:{file:bool}, deps_ok:bool}。"""
    if not repo_root:
        return {"deps": {}, "deps_ok": False}
    name = os.path.basename(repo_root.rstrip("/\\"))
    need = _REQUIRED_LIBS.get(name, {})
    deps = {}
    for rel in need:
        deps[rel] = os.path.exists(os.path.join(repo_root, rel))
    return {"deps": deps, "deps_ok": all(deps.values()) if deps else True}


def check_required(repo_root: str | None, clear: bool = True) -> dict:
    """校验兄弟仓库关键依赖文件是否在位；缺失给出清晰报错列表。

    返回 {present, missing:[{file, role, fix}], ok}。缺失不抛出、调用方回退，
    但绝不静默——missing 非空即代表该仓库能力不可用，需明确处理。
    """
    if not repo_root:
        return {"present": False, "missing": [],
                "ok": False, "error": "未发现兄弟仓库（可经环境变量 FACTORY_ONTOLOGY_KIT_DIR / SME_DECISION_ONTOLOGY_DIR 指定）"}
    name = os.path.basename(repo_root.rstrip("/\\"))
    need = _REQUIRED_LIBS.get(name, {})
    missing = []
    for rel, role in need.items():
        if not os.path.exists(os.path.join(repo_root, rel)):
            missing.append({"file": rel, "role": role,
                            "fix": f"仓库 {name} 缺少 {rel}，请拉取完整仓库或补建该文件"})
    return {"present": True, "missing": missing, "ok": not missing,
            "repo": name}


def verify_linkage() -> dict:
    """跨开源联动健壮性总检：定位 + 依赖检测 + 缺失清晰报错 + 可用能力。

    供 linkage op 与跨开源组装链在启动时调用：任兄弟仓库缺关键依赖文件，
    会清晰列出 missing，链路回退为「单库/零库」可用，不崩溃。
    """
    f = find_factory()
    s = find_sme()
    f_ck = check_required(f)
    s_ck = check_required(s)
    return {
        "factory_ontology_kit": {
            **({"dir": f} if f else {}),
            "present": f is not None,
            "deps_ok": f_ck["ok"],
            "missing": f_ck["missing"],
        },
        "sme_decision_ontology": {
            **({"dir": s} if s else {}),
            "present": s is not None,
            "deps_ok": s_ck["ok"],
            "missing": s_ck["missing"],
        },
        "available": (f is not None and f_ck["ok"]) or (s is not None and s_ck["ok"]),
        "fallback": "任库缺依赖/缺失 → 该库能力回退为不可用，不阻断 solo 主链",
    }

