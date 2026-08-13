# -*- coding: utf-8 -*-
"""code_review.py — 代码审查原子能力（对齐 codeagent-minimal，纯标准库零依赖）。

本模块把 codeagent-minimal (zhengjinjun1975/codeagent-minimal, review.py) 的代码审查
原子能力逐字移植合并到 solo，使 solo 具备与 codeagent 同一套审查方法论与评分口径：

- 静态分析(纯 AST/regex，零模型): 语法 / 未用 import / 圈复杂度 / 命名规范 /
  软件 BUG(裸except/可变默认参数/==None) / 架构(文件过大/函数过长/import过多) /
  安全(SQL注入/命令注入/eval-exec/硬编码密钥/反序列化) / 网络(SSRF/明文HTTP/URL凭证) /
  复用优先(冗余抽象/转发函数/重复字符串/过度类包装)
- 0-100 评分: score = max(0, 100 - Σ severity权重)，critical=20/major=10/minor=3/info=1，
  与 codeagent `_static_analyze` 完全一致，保证同一文件两边得分相同。

codeagent-minimal 在 GitHub 保留独立库；此处仅复用其原子能力统一两库口径。
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

# ═══════════════════════════════════════════════════
# 评分口径（与 codeagent 一致）
# ═══════════════════════════════════════════════════
SEVERITY_WEIGHTS = {"critical": 20, "major": 10, "minor": 3, "info": 1}


def _static_check_syntax(content: str) -> list:
    try:
        ast.parse(content)
        return []
    except SyntaxError as e:
        return [{"severity": "critical", "title": f"语法错误: {e.msg}",
                 "line": e.lineno, "suggestion": str(e)}]


def _static_check_imports(tree, content: str) -> list:
    issues = []
    imports = {}
    used_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports[alias.asname or alias.name] = node.lineno
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used_names.add(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used_names.add(node.value.id)
    for name, lineno in imports.items():
        if name.split(".")[0] not in used_names:
            issues.append({"severity": "minor", "title": f"未使用的 import: {name}",
                           "line": lineno, "suggestion": "删除未使用的 import"})
    return issues


def _static_check_complexity(tree, max_complexity: int = 10) -> list:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            c = 1
            branches = 0
            for n in ast.walk(node):
                if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                  ast.And, ast.Or, ast.Assert, ast.Try)):
                    c += 1
                    branches += 1
            if c > max_complexity:
                kind = "分支复杂" if branches > 5 else "整体复杂"
                issues.append({"severity": "major", "title": f"圈复杂度 {c} > {max_complexity} ({kind}): {node.name}",
                               "line": node.lineno, "suggestion": f"分支多可拆分；纯长逻辑可用 --max-complexity 放宽"})
    return issues


def _static_check_naming(tree) -> list:
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            if not re.match(r'^[a-z_]\w*$', node.name):
                issues.append({"severity": "minor", "title": f"函数名建议小写: {node.name}",
                               "line": node.lineno, "suggestion": f"改名 {node.name.lower()}"})
        elif isinstance(node, ast.ClassDef):
            if not re.match(r'^[A-Z]\w*$', node.name):
                issues.append({"severity": "minor", "title": f"类名建议大写开头: {node.name}",
                               "line": node.lineno, "suggestion": f"改名 {node.name.capitalize()}"})
    return issues


def _static_check_bugs(tree, content: str, strict_undefined: bool = False) -> list:
    """软件 BUG 检测：裸 except/可变默认参数/==None；undefined-name 默认关闭(strict 才查)。"""
    issues = []
    # 裸 except / 空 except
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({"severity": "major", "title": "裸 except（吞掉所有异常）",
                           "line": node.lineno, "suggestion": "指定异常类型，如 except ValueError:"})
    # 可变默认参数（经典 bug：共享可变对象）
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for d in node.args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    issues.append({"severity": "major", "title": f"可变默认参数: {node.name}()",
                                   "line": node.lineno, "suggestion": "用 None 作默认，函数内初始化"})
    # == None 应 is None
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) and comp.value is None:
                    issues.append({"severity": "minor", "title": "== None 应写 is None",
                                   "line": node.lineno, "suggestion": "用 `is None` 判断"})
    # 未定义名（默认关闭，启发式易误报，仅 strict 启用）
    if strict_undefined:
        defined = set()
        loaded = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defined.add(node.name)
                for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                    defined.add(a.arg)
                if node.args.vararg:
                    defined.add(node.args.vararg.arg)
                if node.args.kwarg:
                    defined.add(node.args.kwarg.arg)
            elif isinstance(node, ast.ClassDef):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        defined.add(t.id)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                if isinstance(node.target, ast.Name):
                    defined.add(node.target.id)
            elif isinstance(node, ast.ExceptHandler):
                if node.name:
                    defined.add(node.name)
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for g in node.generators:
                    if isinstance(g.target, ast.Name):
                        defined.add(g.target.id)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    defined.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    defined.add(a.asname or a.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loaded.add(node.id)
        builtins = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
        for n in loaded - defined - builtins - {"self", "cls", "__name__", "__file__"}:
            if n in {"if", "for", "in", "or", "and", "not"}:
                continue
            issues.append({"severity": "info", "title": f"可能未定义: {n}", "line": 0,
                           "suggestion": f"确认 {n} 已定义或导入（启发式，可能误报）"})
    return issues


def _static_check_architecture(content: str) -> list:
    """架构稳健评估：文件过大、函数过长、import 依赖过多。"""
    issues = []
    lines = content.split("\n")
    if len(lines) > 500:
        issues.append({"severity": "major", "title": f"文件过大({len(lines)}行)",
                       "line": 0, "suggestion": "考虑拆分为多模块"})
    try:
        tree = ast.parse(content)
        imports = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)))
        if imports > 15:
            issues.append({"severity": "minor", "title": f"import 依赖过多({imports}个)",
                           "line": 0, "suggestion": "检查是否过度依赖"})
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                size = (node.end_lineno or node.lineno) - node.lineno
                if size > 60:
                    issues.append({"severity": "major", "title": f"函数过长({size}行): {node.name}",
                                   "line": node.lineno, "suggestion": "拆分为多个小函数"})
    except SyntaxError:
        pass
    return issues


def _static_check_network(content: str) -> list:
    """网络安全隐患：SSRF/明文HTTP/URL含凭证/网络数据执行/不安全配置。"""
    issues = []
    # SSRF：请求 URL 来自变量（若用户可控则 SSRF 风险）
    if re.search(r'(requests\.(get|post|put|delete|head)\s*\(\s*[a-zA-Z_][a-zA-Z0-9_]*)', content):
        issues.append({"severity": "major", "title": "SSRF 风险(请求URL为变量)",
                       "line": 0, "suggestion": "若 URL 来自用户输入，攻击者可探测内网；校验协议/域名白名单"})
    if re.search(r'urllib\.request\.urlopen\s*\(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\)', content):
        issues.append({"severity": "major", "title": "SSRF 风险(urlopen 变量URL)",
                       "line": 0, "suggestion": "校验 URL 协议与域名，防内网探测"})
    # 明文 HTTP（非 TLS）
    if re.search(r'["\']http://[^"\'\s]+', content) and not re.search(r'https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)', content):
        issues.append({"severity": "major", "title": "明文 HTTP（应用 HTTPS）",
                       "line": 0, "suggestion": "生产环境用 https://，避免明文传输敏感数据"})
    # URL 内嵌凭证（http://user:pass@）
    if re.search(r'https?://[^@\s/:]+:[^@\s/]+@', content):
        issues.append({"severity": "critical", "title": "URL 内嵌明文凭证",
                       "line": 0, "suggestion": "凭证不要写进 URL，用环境变量/密钥管理"})
    # 网络获取数据直接执行（eval/exec/__import__ 接收网络数据）
    if re.search(r'(response\.text|\.content|requests\.get[^)]*\))\s*[^\n]{0,40}(eval|exec|__import__)', content, re.S):
        issues.append({"severity": "critical", "title": "网络数据直接执行(eval/exec)",
                       "line": 0, "suggestion": "不可信网络数据不要 eval/exec，用安全解析"})
    # 不安全配置
    if re.search(r'DEBUG\s*=\s*True', content):
        issues.append({"severity": "major", "title": "DEBUG=True 泄漏调试信息",
                       "line": 0, "suggestion": "生产环境关闭 DEBUG"})
    if re.search(r'ALLOWED_HOSTS\s*=\s*\[?\s*["\']\*', content):
        issues.append({"severity": "major", "title": "ALLOWED_HOSTS=*（Host 头注入）",
                       "line": 0, "suggestion": "限定允许的 Host"})
    # shell 网络命令（curl/wget）带变量
    if re.search(r'(curl|wget)\b[^)\n]{0,40}[\+\{]', content):
        issues.append({"severity": "major", "title": "shell 网络命令拼接",
                       "line": 0, "suggestion": "避免用 shell 拼 curl/wget，用参数列表"})
    return issues


def _static_check_security(content: str) -> list:
    issues = []
    # SQL 注入（区分大小写匹配 SQL 关键字，避免 list.insert/dict.update 误判）
    if re.search(r'\b(SELECT|INSERT|UPDATE|DELETE)\b.*?(f["\']|\+\s*["\'a-zA-Z_]|%["\']|\.format\(|\{[^}]*\})', content, re.S):
        issues.append({"severity": "critical", "title": "SQL 注入风险",
                       "suggestion": "用参数化查询/占位符，避免将变量直接拼进 SQL"})
    if re.search(r'subprocess\.[a-z]+\([^)]*shell\s*=\s*True', content, re.I):
        issues.append({"severity": "critical", "title": "命令注入风险(shell=True)",
                       "suggestion": "避免 shell=True；用参数列表传命令，勿拼接用户输入"})
    if re.search(r'os\.system\s*\([^)]*[\+\{]', content):
        issues.append({"severity": "major", "title": "命令拼接风险",
                       "suggestion": "os.system 传动态字符串易注入，改用 subprocess 参数列表"})
    if re.search(r'os\.system\s*\(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\)', content):
        issues.append({"severity": "major", "title": "命令注入风险(os.system变量)",
                       "suggestion": "os.system(变量) 会执行变量内容，改用 subprocess.run 参数列表"})
    if re.search(r'\beval\s*\([^)]*\)|\bexec\s*\([^)]*\)', content):
        issues.append({"severity": "major", "title": "不安全的 eval/exec",
                       "suggestion": "避免对不可信输入执行 eval/exec；用 ast.literal_eval 等安全替代"})
    if re.search(r'\b(password|passwd|secret|api_key|apikey|token|client_secret)\s*=\s*["\'][^"\']{6,}', content, re.I):
        issues.append({"severity": "major", "title": "硬编码密钥/密码",
                       "suggestion": "密钥不要写死在代码，改用环境变量/配置文件"})
    if re.search(r'pickle\.loads|yaml\.load\s*\([^)]*\)(?!\s*,\s*Loader)', content):
        issues.append({"severity": "major", "title": "不安全的反序列化",
                       "suggestion": "pickle/yaml.load 可执行任意代码，改用安全 Loader 或 JSON"})
    return issues


def _strip_self_check_code(content: str) -> str:
    """剔除安全检查函数自身的源码区间，修复"扫描器扫到自己"的自指误报。"""
    try:
        tree = ast.parse(content)
        targets = {"_static_check_security", "_static_check_network", "_strip_self_check_code"}
        lines = content.split("\n")
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in targets:
                lines[node.lineno - 1:node.end_lineno] = [""] * (node.end_lineno - node.lineno + 1)
        return "\n".join(lines)
    except SyntaxError:
        pass
    return content


def _static_check_reuse(tree, content: str) -> list:
    """复用优先·极简落地审查维度。

    检查代码是否违反方法论：能复用却重写、该极简却过度抽象、重复实现。
    """
    issues = []
    try:
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        # 1. 函数体过短却独立成函数（不必要的抽象）
        for fn in funcs:
            body_len = sum(1 for s in ast.walk(fn) if isinstance(s, ast.stmt))
            if body_len <= 2 and fn.name.startswith("_"):
                issues.append({"severity": "minor", "title": f"冗余抽象: 函数 {fn.name} 体过短({body_len}句), 可内联", "line": fn.lineno})
        # 2. 纯转发函数（仅调用另一函数，无附加值）→ 极简落地应内联/复用
        for fn in funcs:
            calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
            if len(calls) == 1 and len(fn.body) == 1 and isinstance(fn.body[0], (ast.Return, ast.Expr)):
                # 参数都是简单标识符（ast.arg 类型），且不含默认值/复杂结构
                simple_args = all(not a.arg.startswith("_") for a in fn.args.args) and not fn.args.vararg and not fn.args.kwarg
                if simple_args:
                    issues.append({"severity": "minor", "title": f"转发函数 {fn.name}: 仅调用一次, 考虑直接复用调用点", "line": fn.lineno})
        # 3. 重复字符串常量（同一字面量出现≥3次 → 应提取常量复用）
        str_lits = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= 4]
        for s, cnt in Counter(str_lits).most_common(3):
            if cnt >= 3:
                issues.append({"severity": "minor", "title": f"重复字符串 '{s}' 出现{cnt}次, 建议提取常量复用", "line": 1})
        # 4. 不必要的类包装（类仅一个方法且是 __init__ → 过度工程）
        for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
            methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) == 1 and methods[0].name == "__init__":
                issues.append({"severity": "minor", "title": f"过度工程: 类 {cls.name} 仅含 __init__, 可用 dict/简单结构替代", "line": cls.lineno})
    except Exception:
        pass
    return issues


def _static_analyze(content: str, max_complexity: int = 10, strict_undefined: bool = False) -> dict:
    """对单文件执行全量静态分析, 返回结构化结果 + 得分（与 codeagent 口径一致）"""
    result = {"syntax": [], "imports": [], "complexity": [], "naming": [], "security": [],
              "network": [], "bugs": [], "architecture": [], "reuse": [], "score": 100}
    all_issues = []
    result["syntax"] = _static_check_syntax(content)
    all_issues.extend(result["syntax"])
    result["security"] = _static_check_security(_strip_self_check_code(content))
    all_issues.extend(result["security"])
    result["network"] = _static_check_network(_strip_self_check_code(content))
    all_issues.extend(result["network"])
    if not result["syntax"]:
        try:
            tree = ast.parse(content)
            result["imports"] = _static_check_imports(tree, content)
            result["complexity"] = _static_check_complexity(tree, max_complexity)
            result["naming"] = _static_check_naming(tree)
            result["bugs"] = _static_check_bugs(tree, content, strict_undefined)
            result["architecture"] = _static_check_architecture(content)
            result["reuse"] = _static_check_reuse(tree, content)
            all_issues.extend(result["imports"] + result["complexity"] + result["naming"]
                              + result["bugs"] + result["architecture"] + result["reuse"])
        except SyntaxError:
            pass
    penalty = sum(SEVERITY_WEIGHTS.get(i["severity"], 5) for i in all_issues)
    result["score"] = max(0, 100 - penalty)
    result["all_issues"] = all_issues
    return result


def review_file(path: str, max_complexity: int = 10, strict_undefined: bool = False) -> dict:
    """审查单文件，返回 {file, static_score, static_issues, issues}（对齐 codeagent review_file）。

    external/reuse-atoms/llm 为 codeagent 可选增强，此处不合并（保留 codeagent 独有）；
    静态评分与 codeagent 完全一致。
    """
    content = Path(path).read_text(encoding="utf-8", errors="ignore")
    static = _static_analyze(content, max_complexity, strict_undefined)
    return {
        "file": path,
        "static_score": static["score"],
        "static_issues": static["all_issues"],
        "issues": [dict(i, file=path) for i in static["all_issues"]],
    }
