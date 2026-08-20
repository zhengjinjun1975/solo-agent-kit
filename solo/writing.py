# -*- coding: utf-8 -*-
"""writing.py — 六维中文写作质量检查（D1-D6）+ 风格改写。

方法论：正确性(fail必改) / 风格(warn建议，保活人感)。
六维：D1错字 / D2标点(fail) / D3语病(fail) / D4数字 / D5去AI味 / D6活人感。

能力双全：
  1. 检测（scan）：合并 zh-writing-checker v3.0 全量规则 + 本地 v1.0 接口兼容
  2. 改写（rewrite + STYLES）：本地独有，按场景风格模板改写（AI 写作助手 写作）
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys

VERSION = "2.0"

# ═══════════════════════ 改写能力（本地独有）═══════════════════════
# 风格模板（对标 AI 写作助手 写作）：不同场景的写作风格约束
STYLES = {
    "tweet": {"name": "推文", "hint": "短小精悍，一句观点+一句佐证+一句行动，无破折号，口语化有活人感",
              "max_len": 280, "rules": ["避免堆砌形容词", "结尾用洞察或反问"]},
    "report": {"name": "报告", "hint": "冷静扎实，句长方差大，数据锚定，结论先行，结尾用洞察不用总结",
               "max_len": 3000, "rules": ["前100字出矛盾不交代结论", "无破折号", "每条观点带证据"]},
    "wechat": {"name": "公众号", "hint": "开头抓人，结构清晰，小标题分段，有故事感，结尾引导互动",
               "max_len": 5000, "rules": ["避免教科书式开头", "多用具体案例"]},
    "paper": {"name": "论文", "hint": "严谨客观，术语准确，逻辑链完整，论证有层次",
              "max_len": 8000, "rules": ["避免口语化", "观点有出处"]},
}

def list_styles() -> dict:
    """返回可用风格模板清单。"""
    return {k: {"name": v["name"], "hint": v["hint"]} for k, v in STYLES.items()}


def generate_doc(topic: str, kind: str = "readme", tier: str = "local") -> str:
    """生成工程文档（并入自 gen.py 文档生成部分）。kind: readme / changelog / docstring / guide。"""
    from solo import provider as provider_mod
    p = provider_mod.Provider.from_file()
    templates = {
        "readme": "为以下项目写一个简洁 README（定位/快速开始/能力/限制/致谢）",
        "changelog": "写一个 CHANGELOG 的 0.1.0 段（新增/修复/方法论）",
        "docstring": "为以下代码写 docstring（中文，说明用途/参数/返回）",
        "guide": "写一个使用指南（清晰步骤，面向新人）",
    }
    tpl = templates.get(kind, templates["readme"])
    sys_prompt = f"{tpl}:\n{topic}\n\n遵守：中文，简洁，诚实，不夸大。"
    return p.complete(sys_prompt, tier=tier)


# ═══════════════════════ AI味自检（接入 zh-writing-checker）═══════════════════════
# zh_ai_taste.py 已并入本模块（同一「写作检查」概念域），单一写作检查入口。

# ── 定位 zh-writing-checker 单文件模块 ─────────────────────────────
# 候选路径：环境变量 → 常见源码根。任一命中即可，找不到不报错。
_CANDIDATES = [
    os.environ.get("ZH_WRITING_CHECKER", ""),
]
# 相对回退：从本文件往上找 open-source 根（保证闭源工具在 E: 根即可命中）
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(4):
    _p = os.path.join(os.path.dirname(_here), *([".."] * _up),
                      "open-source", "zh-writing-checker", "zh_writing_checker.py")
    _CANDIDATES.append(os.path.normpath(_p))
_CANDIDATES = [p for p in _CANDIDATES if p]

_LOADED = None  # 模块对象 or None（未加载）；失败不缓存，避免返回 False
_LOAD_TRIED = False


def _locate() -> str:
    for p in _CANDIDATES:
        if p and os.path.isfile(p):
            return p
    return ""


def _load():
    """动态加载 zh-writing-checker 模块（单文件，无第三方依赖）。找不到返回 None。

    始终返回「模块对象 或 None」，绝不返回 bool —— 曾因缓存 False 导致
    第二次调用拿到 False、`mod.human_gate` 报 "'bool' object has no attribute"。
    """
    global _LOADED, _LOAD_TRIED
    if _LOADED is not None:
        return _LOADED
    if _LOAD_TRIED:
        # 已尝试过且失败，直接 None（不重复加载，但返回类型恒为模块/None）
        return None
    _LOAD_TRIED = True
    path = _locate()
    if not path:
        return None
    try:
        spec = importlib.util.spec_from_file_location("_zh_writing_checker_rt", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LOADED = mod
    except Exception:
        return None
    return _LOADED


def _penalty(sev, count):
    """各层级问题的AI味惩罚权重（主观项轻罚，客观错字/语病重罚提示必改）。"""
    w = {"fail": 3.0, "warn": 1.5, "info": 0.5}.get(sev, 1.0)
    return w * max(1, int(count or 1))


def ai_taste_report(text: str, style: str = "report") -> dict:
    """对一段文本做 AI 味检测 + 建议，返回结构化 dict。

    text: 待检中文文本。style: report/wechat/tweet/paper（仅用于提示措辞）。
    返回字段：
      ok / available  是否成功接入 zh-writing-checker
      human           人味门检结果（真人文本 True）
      register        语体识别
      ai_score        100为最像人，越低越AI腔
      hard_fails      语言层(L1)必改项数（错字/标点/语病/数字）
      soft_warns      D5/D6 建议项数
      issues          命中问题（含建议）
      suggestions     可执行改写建议列表
    """
    mod = _load()
    base = {
        "ok": False, "available": False, "human": None, "register": None,
        "ai_score": None, "hard_fails": 0, "soft_warns": 0,
        "issues": [], "suggestions": [], "note": "zh-writing-checker 未接入（未定位到模块）",
    }
    if mod is None:
        return base

    try:
        gate = mod.human_gate(text)
        register = mod.register_of(text)
        scan = mod.scan_text(text)
    except Exception as e:  # noqa: BLE001
        base["note"] = f"检测异常: {e}"
        return base

    # 汇总问题
    issues = list(scan.get("issues", []))
    hard_fails = sum(1 for i in issues if i.get("layer") in ("D1", "D2", "D3", "D4")
                     and i.get("severity") == "fail")
    soft_warns = sum(1 for i in issues if i.get("layer") in ("D5", "D6"))

    # AI味分：门检真人→高分；否则按 D5/D6 惩罚
    ai_score = 100.0
    if gate and gate.get("human"):
        ai_score = 95.0
    else:
        for i in issues:
            if i.get("layer") in ("D5", "D6"):
                ai_score -= _penalty(i.get("severity", "warn"), i.get("count", 1))
    ai_score = max(0.0, min(100.0, round(ai_score, 1)))

    # 改写建议（只提示不强制）
    suggestions = []
    for i in issues:
        sug = i.get("suggestion") or ""
        if sug:
            suggestions.append(f"[{i.get('layer')}] {i.get('type')}: {sug}")

    result = {
        "ok": True, "available": True,
        "human": bool(gate and gate.get("human")),
        "register": register,
        "ai_score": ai_score,
        "hard_fails": hard_fails, "soft_warns": soft_warns,
        "issues": issues, "suggestions": suggestions,
        "note": f"AI味分 {ai_score}（100=最像人）",
    }
    # 自洽结论：score/fail/建议 三者不矛盾（P2-8）
    if hard_fails:
        result["verdict"] = f"存在 {hard_fails} 项 L1 必改问题（错字/标点/语病/数字），需修正后再定稿，勿仅凭 AI 味分判断"
    elif ai_score >= 80:
        result["verdict"] = "自然，可定稿"
    elif ai_score >= 60:
        result["verdict"] = "略AI腔，建议按提示打磨后再定稿"
    else:
        result["verdict"] = "AI腔明显，建议按提示改写后再定稿"
    if gate and gate.get("human"):
        result["note"] = "命中真人文本，停手不改声口。" + result["note"]
    return result


def format_ai_report(report: dict, source: str = "文本") -> str:
    """把 ai_taste_report 渲染为人类可读的提示（打印/日志用）。"""
    if not report.get("ok"):
        return f"[AI味自检] {source}: {report.get('note', '未接入')}"
    lines = []
    level = ("自然" if report["ai_score"] >= 80 else
             "略AI腔" if report["ai_score"] >= 60 else "AI腔明显")
    lines.append(f"[AI味自检] {source}: 分 {report['ai_score']}（{level}）"
                 f" | L1必改 {report['hard_fails']} 项 | D5/D6建议 {report['soft_warns']} 项")
    if report["register"]:
        lines.append(f"  语体识别: {report['register']}")
    if report["human"]:
        lines.append("  人味门检: 命中真人文本，停手不改声口。")
    sugs = report["suggestions"]
    if sugs:
        lines.append("  建议（不强制，按需取舍）:")
        for s in sugs[:8]:
            lines.append(f"    - {s}")
    else:
        lines.append("  未发现需改写项。")
    return "\n".join(lines)


def ai_taste(text: str, style: str = "report") -> dict:
    """AI味自检：检测 AI 腔，返回评分+建议（零依赖）。

    接入生态：让 solo 写作产出先过一遍"人味门检→两层检测"，
    给出 AI 味分（100=最像人）与可执行改写建议，只提示不强制改写。
    """
    return ai_taste_report(text, style=style)


def format_ai_taste(report: dict, source: str = "文本") -> str:
    """把 ai_taste 结果渲染为人类可读提示。"""
    return format_ai_report(report, source=source)


def write_natural(text: str, style: str = "tweet", provider=None) -> dict:
    """生成→AI味检测→改写建议→复检 闭环，产出对齐风格的更自然文本。

    流程:
      1. 检测 AI 味（zh-writing-checker）
      2. 若可用 provider：按风格改写；否则返回风格指导 + 检测建议
      3. 对结果复检，给出前后 AI 味分对比
    不强制改写——检测到自然文本或未接入检查器时，如实说明。
    """
    report = ai_taste(text, style)
    # 即使未接入检查器，也执行改写（无 provider 返回原文+风格指导），
    # 保证 write_natural 始终产出 rewrite（对 CLI 场景 rewritten 非空）
    r = rewrite(text, style, provider)  # 风格改写（本地模板/LLM）
    rewritten = r.get("rewritten") or ""
    if not rewritten and provider is None:
        # 无 provider：本地模式，直接返回原文 + 风格指导
        r = dict(r, rewritten=text, rewritten_len=len(text),
                 note="未配置 provider，返回原文+风格指导；配置 provider 后可自动改写")
        rewritten = text
    recheck = ai_taste(rewritten, style) if rewritten else None
    before_score = report.get("ai_score") if report.get("ok") else None
    after_score = recheck.get("ai_score") if (recheck and recheck.get("ok")) else None
    return {
        "style": style,
        "ai_taste_before": report,
        "rewrite": r,
        "ai_taste_after": recheck,
        "improvement": None if (before_score is None or after_score is None)
                       else round(after_score - before_score, 1),
        "note": "建议已给出（提示不强制）；若 AI 味分高，可用 provider 自动改写或按建议手动打磨。",
    }

def rewrite(text: str, style: str = "tweet", provider=None) -> dict:
    """按风格模板改写文本（对标 AI 写作助手 写作）。

    style: tweet/report/wechat/paper
    provider: 可选 LLM provider；无则用规则提示（返回风格指导）。
    """
    s = STYLES.get(style, STYLES["tweet"])
    if provider:
        prompt = (f"请把下面文本改写成{s['name']}风格。\n"
                  f"风格要求：{s['hint']}\n规则：{'；'.join(s['rules'])}\n"
                  f"保持原意，输出改写后的中文，不要解释。\n\n原文：\n{text}")
        try:
            out = provider.complete(prompt, tier="local")
            return {"style": style, "style_name": s["name"], "rewritten": out,
                    "original_len": len(text), "rewritten_len": len(out or "")}
        except Exception:
            pass
    return {"style": style, "style_name": s["name"], "rewritten": "",
            "hint": s["hint"], "rules": s["rules"],
            "original_len": len(text), "max_len": s["max_len"],
            "note": "未配置 LLM，返回风格指导；配置 provider 后可自动改写"}

# ═══════════════════════ 检测规则（合并 zh-writing-checker v3.0）═══════════════════════

# ── D1 常见错别字对（近音/近形，warn）──
COMMON_TYPO_PAIRS = [
    ("必需", "必须"), ("做为", "作为"),
    ("帐本", "账本"), ("座落", "坐落"), ("寒喧", "寒暄"),
    ("精萃", "精粹"), ("幅射", "辐射"), ("振撼", "震撼"),
    ("痉孪", "痉挛"), ("决窍", "诀窍"), ("脉博", "脉搏"),
    ("装祯", "装帧"), ("渡假", "度假"), ("按排", "安排"),
    ("既使", "即使"), ("既而", "继而"), ("以经", "已经"),
    ("利害关系", "厉害关系"), ("做为一个", "作为一个"),
]
# 异形词（《第一批异形词整理表》推荐写法）: (非推荐, 推荐)
VARIANT_WORDS = [
    ("交待", "交代"), ("必恭必敬", "毕恭毕敬"), ("当做", "当作"),
    ("缘份", "缘分"), ("澈底", "彻底"), ("谋画", "谋划"),
    ("胡涂", "糊涂"), ("含意", "含义"), ("人材", "人才"),
    ("思惟", "思维"), ("制做", "制作"), ("抹煞", "抹杀"),
    ("想像", "想象"), ("联贯", "连贯"), ("彷佛", "仿佛"),
    ("归根结柢", "归根结底"), ("装璜", "装潢"),
    ("跌荡", "跌宕"), ("故技重演", "故伎重演"),
]

# ── D2 标点规范（GB/T 15834，fail）──
EN_PUNCT_IN_CN = {",": "，", ".": "。", "?": "？", "!": "！", ";": "；", ":": "：", '"': "“”"}
# 半角标点紧跟中文（应全角）
HALF_PUNCT = re.compile(r"[\u4e00-\u9fff][,.;:!?](?=[\u4e00-\u9fff])")
# 中英标点混用
MIXED_PUNCT = re.compile(r"[\u4e00-\u9fff][,.;:!?()]")

# ── D3 语法语病（常见病句，fail）──
FAULTY_PATTERNS = [
    ("成分残缺·通过…使", r"通过[^。，；]{2,30}(使|让|令)", "“通过…使”双介词，主语残缺，删其一"),
    ("成分残缺·缺主语", r"^(经过|随着|由于)[^。]{5,40}(终于|才|便)", "句首介词短语后缺主语"),
    ("搭配不当·改善…水平", r"改善[^。]{0,8}(水平|程度)", "“改善”搭配“状况/条件”，不用“水平”"),
    ("搭配不当·提高…数量", r"提高[^。]{0,8}(数量)", "“提高”搭配“质量/水平”，数量用“增加/提升”"),
    ("句式杂糅·是因为…原因", r"是因为[^。]{0,15}的原因", "“是因为…的原因”杂糅，删“的原因”"),
    ("句式杂糅·目的是为了", r"目的是为了", "“目的是为了”杂糅，删“为了”或“目的”"),
    ("句式杂糅·由于…所致", r"由于[^。]{0,20}所致", "“由于…所致”杂糅，删“所致”"),
    ("前后矛盾·大约…左右", r"大约[^。]{0,10}左右", "“大约…左右”语义重复，删一"),
    ("前后矛盾·几乎…都", r"几乎[^。]{0,10}(全部|都)", "“几乎…都”矛盾，二选一"),
    ("句式杂糅·关键在于…在于", r"关键在于[^。]{0,10}在于", "“关键在于…在于”重复"),
    ("成分残缺·对…进行", r"对[^。]{2,30}进行(了)?$", "“对…进行”缺宾语或冗余"),
]

# ── D4 数字规范（GB/T 15835，warn）──
DATE_FMT = re.compile(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}")
RANGE_TILDE = re.compile(r"\d+~\d+")
CN_CN_NUM = re.compile(r"[\u4e00-\u9fff][0-9]+|(?<![0-9])[0-9]+[\u4e00-\u9fff]")

# ── D5 文风/去AI味（warn+fail）──
DISABLED_WORDS = [
    "底层逻辑", "赋能", "闭环", "长期主义", "关键抓手", "价值沉淀", "认知升级",
    "说白了", "本质上", "综上所述", "值得注意的是", "不难发现",
    "无需多言", "归根结底", "众所周知", "显然", "毫无疑问", "某种意义上",
    "抓手", "破局", "降维打击", "第二曲线", "飞轮", "北极星指标",
    "颗粒度", "同理可得", "打个比方", "毫不夸张地说",
]
META_LANGUAGE = ["写在最后", "结语", "让我们讨论", "总而言之", "在深入探讨之前", "接下来", "言归正传"]
TEXTBOOK_OPENERS = ["在当今时代", "随着……发展", "众所周知", "毋庸置疑", "进入新世纪", "随着科技的进步"]
STYLE_PATTERNS = [
    (r"不是[^。，]{1,20}而是", "句式指纹：不是…而是"),
    (r"从[^。，]{1,10}到[^。，]{1,10}", "句式指纹：从…到…"),
    (r"不仅[^。，]{1,20}更是", "句式指纹：不仅…更是"),
    (r"(首先|其次|最后|第一|第二|第三)", "流水账序号，可用转场句"),
    (r"AI工具|某个模型|相关技术|一些方法", "空泛工具名，应说具体名字"),
    (r"比如有一次|假设你|想象一下", "假想例子（可能编造场景）"),
]
DEAD_VERBS = ["进行", "实现", "达到", "提升", "降低", "增加", "减少", "拥有", "属于", "涉及", "相关的", "所谓的"]
DASH_PATTERN = re.compile(r"——|—{1,2}|–{1,2}")

# ── D6 活人感/可读性 ──
CONNECTIVES = ["然而", "此外", "同时", "因此", "总之", "综上", "进而", "从而", "并且", "而且", "再者", "换言之"]
LONG_PARAGRAPH = 400    # 字
FLAT_SENTENCE_DELTA = 5  # 连续句长字数差阈值

# ── 工具 ──
def _strip_code_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)

def _contexts(text: str, needle: str, width: int = 22, max_items: int = 3) -> list:
    out, start = [], 0
    while True:
        i = text.find(needle, start)
        if i < 0:
            break
        out.append(text[max(0, i - width):i + len(needle) + width].replace("\n", " "))
        if len(out) >= max_items:
            break
        start = i + len(needle)
    return out

def _split_sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"[。！？!?；]", text) if s.strip()]


def _scan_d1(text, _add):
    """D1 错字/错词（warn）。"""
    for wrong, right in VARIANT_WORDS:
        if wrong != right and wrong in text:
            _add("D1", f"异形词: {wrong}（规范:{right}）", text.count(wrong), "warn",
                 f"建议用规范写法 {right}", _contexts(text, wrong, 15, 2))
    for wrong, right in COMMON_TYPO_PAIRS:
        if wrong != right and wrong in text:
            _add("D1", f"疑似错字: {wrong}", text.count(wrong), "warn",
                 f"请复核是否应写 {right}", _contexts(text, wrong, 15, 2))
    en_mix = re.findall(r"[\u4e00-\u9fff][A-Za-z]{3,}[\u4e00-\u9fff]", text)
    if en_mix:
        _add("D1", "中英混写", len(en_mix), "info", "中文句夹英文，注意空格与术语统一", en_mix[:3])


def _scan_d2(text, _add):
    """D2 标点（fail）。"""
    for m in HALF_PUNCT.finditer(text):
        c = text[m.start() + 1]
        _add("D2", f"半角标点{c}(应全角)", 1, "fail",
             f"改用中文标点 {EN_PUNCT_IN_CN.get(c, c)}", [text[max(0, m.start()-10):m.start()+12]])
    for m in MIXED_PUNCT.finditer(text):
        c = text[m.start() + 1]
        if c in EN_PUNCT_IN_CN:
            _add("D2", f"中英标点混用:'{c}'", 1, "fail",
                 f"改用全角 {EN_PUNCT_IN_CN[c]}", [text[max(0, m.start()-10):m.start()+12]])
    for m in re.finditer(r'[\u4e00-\u9fff]"[^"]{1,20}"', text):
        _add("D2", "英文引号", 1, "fail", "中文引号用“”", [m.group(0)[:40]])


def _scan_d3(text, _add):
    """D3 语病（fail）。"""
    for name, pat, sug in FAULTY_PATTERNS:
        for m in re.finditer(pat, text):
            _add("D3", name, 1, "fail", sug, [m.group(0)[:40]])


def _scan_d4(text, _add):
    """D4 数字（warn）。"""
    for m in DATE_FMT.finditer(text):
        _add("D4", f"日期格式:{m.group(0)}", 1, "warn", "日期建议用 YYYY-MM-DD 或中文年月日", [m.group(0)])
    for m in RANGE_TILDE.finditer(text):
        _add("D4", f"范围用~:{m.group(0)}", 1, "warn", "范围用全角连接号或'至'", [m.group(0)])
    for m in CN_CN_NUM.finditer(text):
        _add("D4", f"中英数字混排:{m.group(0)}", 1, "warn", "数字书写统一", [m.group(0)])


def _scan_d5(text, _add):
    """D5 去AI味（warn + fail 破折号/禁用词）。"""
    for w in DISABLED_WORDS:
        if w in text:
            _add("D5", f"禁用词:{w}", text.count(w), "fail", "换成具体描述", _contexts(text, w, 18, 2))
    for w in META_LANGUAGE:
        if w in text:
            _add("D5", f"元语言:{w}", text.count(w), "warn", "删掉或改自然转场", _contexts(text, w, 18, 2))
    for w in TEXTBOOK_OPENERS:
        if w in text:
            _add("D5", f"教科书开头:{w}", text.count(w), "warn", "开头直接给结论", _contexts(text, w, 18, 2))
    for pat, label in STYLE_PATTERNS:
        for m in re.finditer(pat, text):
            _add("D5", label, 1, "warn", "换个说法，避免模板腔", [m.group(0)[:40]])
    for v in DEAD_VERBS:
        if v in text:
            _add("D5", f"死板动词:{v}", text.count(v), "info", "用有画面感的动词", _contexts(text, v, 15, 1))
    for m in DASH_PATTERN.finditer(text):
        _add("D5", "破折号", 1, "fail", "破折号是AI头号标志，改逗号或重写", [text[max(0, m.start()-10):m.start()+12]])


def _scan_d6(text, _add, stats):
    """D6 活人感（warn + info）。"""
    for i, para in enumerate(text.split("\n")):
        if len(para) > LONG_PARAGRAPH:
            _add("D6", f"超长段落({len(para)}字)", 1, "warn", "拆段，留呼吸感", [para[:40]])
    sents = _split_sentences(text)
    for i in range(len(sents) - 2):
        lens = [len(sents[i]), len(sents[i+1]), len(sents[i+2])]
        if max(lens) - min(lens) < FLAT_SENTENCE_DELTA and max(lens) > 10:
            _add("D6", "句长均匀(无节奏)", 1, "warn", "句长要有变化，长短交错", [" ".join(sents[i:i+3])[:50]])
            break
    conn = sum(text.count(c) for c in CONNECTIVES)
    if stats["total_sentences"] and conn / max(1, stats["total_sentences"]) > 0.3:
        _add("D6", f"连接词过密({conn}/{stats['total_sentences']}句)", conn, "warn", "删冗余连接词", [])
    head = text[:100]
    if stats["total_chars"] > 150 and not re.search(r"\d|结果|结论|是|%|倍|万|亿", head):
        _add("D6", "开篇未给结论", 1, "info", "前100字甩出数字/结论", [head[:60]])


def _build_report(filepath, issues, dim_counts, stats):
    """汇总六维结果 → 结构化报告。"""
    layers = {}
    for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
        di = [i for i in issues if i["layer"] == dim]
        has_fail = any(i["severity"] == "fail" for i in di)
        layers[dim] = {"passed": not has_fail, "issue_count": len(di),
                       "fail_count": sum(1 for i in di if i["severity"] == "fail"),
                       "warn_count": sum(1 for i in di if i["severity"] == "warn")}
    fail_total = sum(1 for i in issues if i["severity"] == "fail")
    return {
        "version": VERSION,
        "file": filepath,
        "total_issues": len(issues), "fail_count": fail_total,
        "warn_count": sum(1 for i in issues if i["severity"] == "warn"),
        "passed": fail_total == 0,
        "dimension_counts": dim_counts, "layers": layers,
        "issues": issues, "stats": stats,
    }


def scan(text: str, filepath: str = None) -> dict:
    """六维扫描，返回结构化报告。text 为要检查的中文文本（兼容 v1 接口）。

    filepath: 可选，填则报告里带文件名（兼容 zh-writing-checker 文件输入）。
    """
    raw = text if filepath is None else open(filepath, encoding="utf-8").read()
    text = _strip_code_blocks(raw)
    issues = []
    stats = {"total_chars": len(raw), "total_sentences": len(_split_sentences(text))}
    dim_counts = {"D1": 0, "D2": 0, "D3": 0, "D4": 0, "D5": 0, "D6": 0}

    def _add(layer, type_, count, severity, suggestion, details=()):
        issues.append({"layer": layer, "type": type_, "count": count,
                       "severity": severity, "suggestion": suggestion, "details": list(details)})
        dim_counts[layer] += count

    _scan_d1(text, _add)
    _scan_d2(text, _add)
    _scan_d3(text, _add)
    _scan_d4(text, _add)
    _scan_d5(text, _add)
    _scan_d6(text, _add, stats)
    return _build_report(filepath, issues, dim_counts, stats)
