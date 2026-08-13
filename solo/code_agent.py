# -*- coding: utf-8 -*-
"""code_agent.py — 代码生成/审查/测试全链路（FDE 核心能力，零依赖）。

方法论（借鉴 CodeAgent，独立实现）：代码生成走远端模型，审查走本地模型，
静态分析 + 生成测试纯标准库 AST。think→implement→review→test 闭环。

模型分层：复用 provider.py（urllib，零依赖）——生成走 remote(DeepSeek)，
审查走 local(ornith)。可降级。

只读能力（不影响工作区）：静态分析/测试生成/run_tests 都是读+临时执行。
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile

from . import code_review  # 代码审查原子能力（对齐 codeagent-minimal：语法/复杂度/安全/0-100评分）

# ── Karpathy / Ponytail 原则注入 ──────────────────────
PONYTAIL_SYSTEM = """你是懒人高级开发者。写代码前爬这个阶梯：
1. YAGNI → 不建
2. 代码库已有 → 复用
3. 标准库有 → 用
4. 平台原生有 → 用
5. 已装依赖有 → 用
6. 一行能搞定 → 一行
7. 不行才写最少代码

硬规则：不加未要求的抽象/依赖/样板。删除>添加。最短diff胜出。
不可偷懒：验证/安全/数据保护。非平凡代码留assert或测试。"""


# ═══════════════════════════════════════════════
# 静态分析工具（对齐 codeagent-minimal，统一到 code_review 单一事实来源）
# 语法/未用import/圈复杂度/命名/软件BUG/架构/安全/网络/复用 + 0-100评分
# ═══════════════════════════════════════════════

# 兼容旧接口：solo 旧版 `_static_analyze` 返回 {issues, counts}；现改为委托
# code_review._static_analyze（与 codeagent 同一套检查+评分口径），并保留 counts。
def _static_analyze(content: str, max_complexity: int = 10, strict_undefined: bool = False) -> dict:
    """综合静态分析（对齐 codeagent）。返回 {issues, counts, score, categories}。"""
    r = code_review._static_analyze(content, max_complexity, strict_undefined)
    issues = r["all_issues"]
    counts = {
        "syntax": len(r["syntax"]),
        "imports": len(r["imports"]),
        "complexity": len(r["complexity"]),
        "naming": len(r["naming"]),
        "security": len(r["security"]) + len(r["network"]),
        "bugs": len(r["bugs"]),
        "architecture": len(r["architecture"]),
        "reuse": len(r["reuse"]),
    }
    return {"issues": issues, "counts": counts, "score": r["score"],
            "categories": {k: r[k] for k in ("syntax", "imports", "complexity", "naming",
                                             "security", "network", "bugs", "architecture", "reuse")}}


# 旧版静态函数保留为兼容别名（同 codeagent 口径，已统一到 code_review）
_static_check_syntax = code_review._static_check_syntax
_static_check_imports = code_review._static_check_imports
_static_check_complexity = code_review._static_check_complexity
_static_check_naming = code_review._static_check_naming
_static_check_security = code_review._static_check_security


# ═══════════════════════════════════════════════
# 测试生成（纯 AST）
# ═══════════════════════════════════════════════

def _extract_type_hint(annotation):
    if annotation is None:
        return ""
    try:
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Constant):
            return str(annotation.value)
        if isinstance(annotation, ast.Index):
            return _extract_type_hint(annotation.value)
        if isinstance(annotation, (ast.Subscript, ast.Tuple, ast.List)):
            return "list"
    except Exception:
        return ""
    return ""


def _is_bool_function(name, node) -> bool:
    return name.startswith("is_") or name.startswith("has_") or name.startswith("can_") or \
        name.startswith("check") or "is_valid" in name


def _boundary_values(hints: dict) -> list:
    """根据类型注解推断边界值。int/float→零+负数；str→空串。"""
    bv = {"int": ["0", "-1"], "float": ["0", "-1.5"], "str": ["''", "'a'"],
          "list": ["[]", "[1]"]}
    return bv.get(hints.get(""), [])


def _gen_python_tests(path, content) -> str:
    """AST 生成参数化测试：基础 + 边界值。"""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    mod = path.replace("/", ".").replace(".py", "").lstrip(".")
    funcs, methods = [], []
    for n in ast.iter_child_nodes(tree):
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            params = [a.arg for a in n.args.args]
            has_return = any(isinstance(x, ast.Return) for x in ast.walk(n))
            hints = {a.arg: _extract_type_hint(a.annotation) for a in n.args.args if a.annotation}
            funcs.append((n.name, params, has_return, hints, n))
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, ast.FunctionDef) and not m.name.startswith("_"):
                    params = [x.arg for x in m.args.args if x.arg not in ("self", "cls")]
                    has_return = any(isinstance(x, ast.Return) for x in ast.walk(m))
                    hints = {a.arg: _extract_type_hint(a.annotation) for a in m.args.args if a.annotation}
                    methods.append((n.name, m.name, params, has_return, hints, m))

    lines = [f'"""tests for {path}"""',
             "import sys; sys.path.insert(0, '.')",
             f"import {mod}", "import pytest", ""]

    for fn, args, hr, hints, node in funcs:
        arglist = ", ".join(["1"] * max(len(args), 1))
        lines += [f"def test_{fn}_basic():", f"    result = {mod}.{fn}({arglist})"]
        if hr:
            lines.append("    assert result is not None")
        lines.append("")
        # 边界值
        for bv in _boundary_values(hints):
            lines += [f"def test_{fn}_boundary_{bv.replace(chr(39),'').replace(chr(45),'neg')}():",
                      f"    result = {mod}.{fn}({bv})", "    assert result is not None", ""]

    for cls, fn, args, hr, hints, node in methods:
        arglist = ", ".join(["1"] * max(len(args), 1))
        lines += [f"def test_{cls}_{fn}_basic():",
                  f"    obj = {mod}.{cls}()", f"    result = obj.{fn}({arglist})"]
        if hr:
            lines.append("    assert result is not None")
        lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# CodeAgent
# ═══════════════════════════════════════════════

class CodeAgent:
    """代码生成/审查/测试全链路（接 solo provider，零依赖）。"""

    def __init__(self, provider=None):
        from solo import provider as pm
        self.provider = provider or pm.Provider.from_file()
        self._reuse_index = {}   # path -> {symbols/deps}(懒加载)

    # ---- 模型调用（适配 provider）----
    def _gen(self, prompt, tier="remote"):
        """生成文本。生成走远端，审查走本地。"""
        return self.provider.complete(prompt, tier=tier)

    # ---- 静态分析（只读，零模型）----
    def analyze(self, code: str) -> dict:
        """静态分析一段代码，返回问题列表。"""
        return _static_analyze(code)

    # ---- think：方案设计 ----
    def think(self, task: str, language="python") -> dict:
        """分析需求，输出方案设计（JSON）。"""
        prompt = (PONYTAIL_SYSTEM + "\n\n分析需求输出 JSON 方案：\n"
                  '{"plan":"一句话","assumptions":[],"files_needed":[],"simplest_approach":""}\n'
                  f"需求：{task}  语言：{language}  极简优先。")
        try:
            out = self._gen(prompt, tier="remote")
            return self._parse_json(out)
        except Exception:
            return {"plan": "直接实现", "files_needed": ["main.py"],
                    "simplest_approach": task}

    # ---- implement：代码生成 ----
    def implement(self, task: str, language="python", loop=False, max_iter=3) -> dict:
        """生成代码。支持 loop 迭代优化（生成→静态审查→改进）。"""
        prompt = (PONYTAIL_SYSTEM + "\n\n"
                  f"用{language}写代码。只输出代码，不要解释。\n任务：{task}")
        code = self._gen(prompt, tier="remote")
        if not code:
            return {"error": "生成失败（模型无返回）"}
        code = self._strip_code_fences(code)

        versions = []
        best = code
        if loop:
            for i in range(max_iter):
                versions.append({"iter": i + 1, "score": self._score_code(best)})
                issues = self._static_issues(best)
                if not issues:
                    break
                # 用问题列表引导改进
                fix_prompt = (PONYTAIL_SYSTEM + "\n\n改进代码，修复以下问题：\n" +
                              "\n".join(f"- {i['title']}" for i in issues[:5]) +
                              f"\n原代码：\n{best}\n输出改进后完整代码。")
                try:
                    new = self._gen(fix_prompt, tier="remote")
                    if new and len(new) > 10:
                        best = new
                except Exception:
                    pass
        return {"files": {"main.py": best}, "score": self._score_code(best),
                "summary": f"生成 {language} 代码", "issues": self._static_issues(best),
                "versions": versions}

    # ---- review：双层审查 ----
    def review(self, code: dict) -> dict:
        """双层审查：静态分析(硬) + 模型审查(软)。code: {文件名: 源码}。"""
        all_issues = []
        for fname, content in (code or {}).items():
            static = _static_analyze(content)
            for i in static["issues"]:
                i["file"] = fname
            all_issues += static["issues"]
        # 模型审查（本地）
        model_issues = []
        try:
            sample = next(iter((code or {}).values()), "")
            if sample:
                out = self._gen(
                    "你是代码审查者。审查代码，指出真实bug/过度工程/可改进处，"
                    "只报真实问题。\n\n" + sample[:3000], tier="local")
                if out and "无问题" not in out and out.strip():
                    model_issues.append({"severity": "info", "title": "模型审查",
                                         "suggestion": out.strip()[:300]})
        except Exception:
            pass
        # 评分对齐 codeagent：score = max(0, 100 - Σ severity权重)
        penalty = sum(code_review.SEVERITY_WEIGHTS.get(i["severity"], 5) for i in all_issues)
        score = max(0, 100 - penalty)
        return {"score": score, "issues": all_issues, "model_issues": model_issues,
                "summary": f"静态{len(all_issues)}条 + 模型审查，评分{score}（对齐codeagent口径）"}

    # ---- test/run_tests ----
    def test(self, code: dict) -> dict:
        """为代码生成测试文件。"""
        tests = {}
        for fname, content in (code or {}).items():
            if fname.endswith(".py"):
                t = _gen_python_tests(fname, content)
                if t:
                    tests[fname.replace(".py", "_test.py")] = t
        return {"test_files": tests}

    def run_tests(self, test_files: dict, workdir=".") -> dict:
        """运行生成的测试。临时目录写入，pytest 执行。"""
        if not test_files:
            return {"ok": False, "error": "无测试文件"}
        tmpdir = tempfile.mkdtemp(prefix="solo_agent_")
        try:
            for name, content in test_files.items():
                path = os.path.join(tmpdir, os.path.basename(name))
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            r = subprocess.run([sys.executable, "-m", "pytest", tmpdir, "-q"],
                               capture_output=True, text=True, timeout=120)
            return {"ok": r.returncode == 0, "exit_code": r.returncode,
                    "output": (r.stdout or "")[-1500:]}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ---- 内部 ----
    def _static_issues(self, code: str) -> list:
        return _static_analyze(code)["issues"]

    def _score_code(self, code: str) -> int:
        # 评分对齐 codeagent：直接取 code_review._static_analyze 的 score
        return code_review._static_analyze(code)["score"]

    def _parse_json(self, text: str) -> dict:
        """从模型输出提取 JSON（markdown 代码块容错）。"""
        if not text:
            return {}
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {}
        try:
            import json
            return json.loads(m.group(0))
        except Exception:
            return {}

    def _strip_code_fences(self, text: str) -> str:
        """去掉模型输出里的 markdown 代码块包裹（```python ... ```）。"""
        if not text:
            return text
        m = re.search(r"```[a-zA-Z]*\n(.*?)```", text, re.S)
        if m:
            return m.group(1).strip()
        return text.strip()
