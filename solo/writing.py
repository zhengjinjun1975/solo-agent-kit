# -*- coding: utf-8 -*-
"""writing.py — 六维中文写作质量检查（D1-D6）+ 风格改写。

方法论：正确性(fail必改) / 风格(warn建议，保活人感)。
六维：D1错字 / D2标点(fail) / D3语病(fail) / D4数字 / D5去AI味 / D6活人感。

能力双全：
  1. 检测（scan）：合并 zh-writing-checker v3.0 全量规则 + 本地 v1.0 接口兼容
  2. 改写（rewrite + STYLES）：本地独有，按场景风格模板改写（OpenClaw 写作）
"""
from __future__ import annotations

import re

VERSION = "2.0"

# ═══════════════════════ 改写能力（本地独有）═══════════════════════
# 风格模板（对标 OpenClaw 写作）：不同场景的写作风格约束
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


# ═══════════ 吸收 qu-ai-wei 方法论：语体识别 + 门检 ═══════════
# 不同语体的"AI 腔"标准完全不同。先识别语体，再选规则，否则会把
# 学术"进行了深入分析"误改口语、把公文"依法予以处理"误改白话。

# 语体指纹（关键字 + 特征正则）→ 语体名
_REGISTER_FINGERPRINTS = {
    "学术/科技": ["论文", "综述", "研究表明", "综上所述", "分析认为", "本研究", "方法论", "机制", "阈值", "显著性"],
    "公文/法律": ["依照", "予以", "兹", "特此", "本办法", "规定", "责令", "行政许可", "依法"],
    "叙事/特稿": ["那时", "我坐在", "他说", "推开门", "记得", "黄昏", "巷子", "她转身"],
    "品牌/广告": ["限时", "即刻", "仅此一次", "秒杀", "爆款", "上新", "为你", "专属"],
    "高考/应试": ["由此可见", "总而言之", "诚然", "不可否认", "值得称道", "排比递进"],
    "社交/口语": ["哈哈", "咱", "贼", "咋", "老铁", "哈喽", "诶", "嘛", "呗", "啦", "啊哈哈"],
    "内容/自媒体": ["家人们", "宝子", "宝们", "姐妹们", "种草", "打卡", "冲鸭", "集美"],
    "商务/职场": ["汇报", "方案", "截止", "跟进", "对接", "本周", "进度", "同步", "请知悉"],
}

# 语体规则：命中多个则取命中数最多的
def _detect_register(text: str) -> str:
    """识别文本语体（9 种）。返回语体名，默认'书面/一般'。"""
    if not text:
        return "书面/一般"
    scores = {}
    for reg, words in _REGISTER_FINGERPRINTS.items():
        scores[reg] = sum(text.count(w) for w in words)
    # 口语 + 方言强信号
    dk = 0
    for w in ["内", "那啥", "咋", "嘛", "呗", "咱"]:
        dk += text.count(w)
    if dk >= 3:
        scores["社交/口语"] = scores.get("社交/口语", 0) + dk
    best = max(scores, key=scores.get) if scores else "书面/一般"
    return best if scores.get(best, 0) >= 2 else "书面/一般"


# 门检：改写前判断是否真人文本（吸收 qu-ai-wei "第负一步"）
# 真人文本的强信号——命中任一条，改写应停手，只清格式不动语言。
_HUMAN_SIGNALS = [
    # 自纠/犹疑/填充语气词
    r"我忘了|我猜啊|不定扯|三十秒还是一分钟|记不清",
    # 地域方言/口语词
    r"咋|贼|那啥|咱|唠嗑|整|老铁|儿化音",
    # meta-irony / 自嘲
    r"用比较酸的话说|听着就不正经|我知道这话|装一把",
    # 具体到只有本人的细节（人名/书名/引用原话）
    r"有人跟我说|那年我|我记得那|我妈说",
]

def _gate_check(text: str) -> dict:
    """门检：判断输入是不是真人写的。

    返回 {"human": bool, "signal": str, "reason": str}
    - human=True: 真人文本（自纠/方言/自嘲/具体细节），改写应停手
    - human=False: AI 生成文本，可继续改写
    """
    for pat in _HUMAN_SIGNALS:
        m = re.search(pat, text)
        if m:
            return {"human": True, "signal": m.group(0),
                    "reason": "命中真人文本强信号（自纠/方言/自嘲/具体细节），停手不改声口"}
    return {"human": False, "signal": "", "reason": "未命中真人信号，可继续改写"}


def rewrite(text: str, style: str = "tweet", provider=None) -> dict:
    """按风格模板改写文本（对标 OpenClaw 写作）。

    style: tweet/report/wechat/paper
    provider: 可选 LLM provider；无则用规则提示（返回风格指导）。

    改写前先门检：若是真人文本，停手返回提示，不改声口。
    """
    # 门检：真人文本停手
    gate = _gate_check(text)
    if gate["human"]:
        return {"style": style, "rewritten": "", "gate": gate,
                "note": "检测到真人文本，不改（避免误改声口）。如需改写请明确说明意图。"}
    # 语体识别（供 style 兜底与提示）
    register = _detect_register(text)
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


def optimize(text: str, style: str = "report", provider=None) -> dict:
    """检测 → 改写 → 复检 闭环（优化器核心入口）。

    流程：
      1. 门检：真人文本停手（不改声口）
      2. 检测：六维 scan 定位 AI 味与质量问题
      3. 改写：按风格模板改写（有 provider 则 LLM 改写，无则返回风格指导）
      4. 复检：对改写结果重新 scan，确认 AI 味/问题是否减少

    返回完整闭环报告。
    """
    # 1. 门检
    gate = _gate_check(text)
    if gate["human"]:
        return {"ok": True, "phase": "gate", "gate": gate,
                "detect": scan(text), "rewrite": None, "recheck": None,
                "note": "检测到真人文本，停手不改声口。"}

    # 2. 检测
    detect = scan(text)

    # 3. 改写
    rw = rewrite(text, style=style, provider=provider)
    rewritten = rw.get("rewritten", "")

    # 4. 复检（仅当改写成功）
    recheck = scan(rewritten) if rewritten else None
    improvement = None
    if recheck and detect.get("fail_count", 0) > 0:
        improvement = detect["fail_count"] - recheck["fail_count"]

    return {"ok": True, "phase": "done", "gate": gate,
            "register": _detect_register(text),
            "detect": detect, "rewrite": rw, "recheck": recheck,
            "improvement": improvement,
            "summary": {
                "before_fail": detect.get("fail_count", 0),
                "after_fail": recheck.get("fail_count", 0) if recheck else None,
                "before_issues": detect.get("total_issues", 0),
                "after_issues": recheck.get("total_issues", 0) if recheck else None,
            }}

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

    # ── D1 错字/错词（warn）──
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

    # ── D2 标点（fail）──
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

    # ── D3 语病（fail）──
    for name, pat, sug in FAULTY_PATTERNS:
        for m in re.finditer(pat, text):
            _add("D3", name, 1, "fail", sug, [m.group(0)[:40]])

    # ── D4 数字（warn）──
    for m in DATE_FMT.finditer(text):
        _add("D4", f"日期格式:{m.group(0)}", 1, "warn", "日期建议用 YYYY-MM-DD 或中文年月日", [m.group(0)])
    for m in RANGE_TILDE.finditer(text):
        _add("D4", f"范围用~:{m.group(0)}", 1, "warn", "范围用全角连接号或'至'", [m.group(0)])
    for m in CN_CN_NUM.finditer(text):
        _add("D4", f"中英数字混排:{m.group(0)}", 1, "warn", "数字书写统一", [m.group(0)])

    # ── D5 去AI味（warn + fail 破折号/禁用词）──
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

    # ── D6 活人感（warn + info）──
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

    # ── 汇总 ──
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
