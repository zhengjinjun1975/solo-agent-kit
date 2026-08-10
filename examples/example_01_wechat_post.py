# -*- coding: utf-8 -*-
"""example_01_wechat_post.py — 一人公司场景①：写公众号推文。

展示 solo 方法论闭环：记忆装载 → 生成 → 六维写作检查 → 提交记忆。
跑法：python examples/example_01_wechat_post.py "主题"

体现"轻≠不行"：零依赖代码跑通"写一篇可用推文"的真实场景。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solo import memory as memory_mod
from solo import skill as skill_mod
from solo import writing as writing_mod
from solo import provider as provider_mod


def main(topic: str):
    print(f"== 场景①：写公众号推文「{topic}」 ==\n")

    # 1. 记忆装载：热域画像 + 相关记忆 + skill
    m = memory_mod.Memory()
    profile = m.profile_text()
    related = m.search(topic, top_k=3)
    sk = skill_mod.Skill()

    # 2. 注入写作 skill（如果已存）
    skill_hint = sk.build_prompt("写公众号推文")

    context = f"主题: {topic}\n\n作者画像:\n{profile}\n\n相关记忆:\n" + \
              "\n".join(f"- {f['text']}" for f in related)
    if skill_hint:
        context += f"\n\n写作经验:\n{skill_hint}"
    context += "\n\n请写一篇200字左右的公众号推文草稿，中文，口语化，有开头钩子。"

    # 3. 生成（本地模型优先）
    print("[1/3] 生成草稿（本地模型）...")
    p = provider_mod.Provider.from_config({})
    draft = p.complete(context, tier="local")
    print(f"\n--- 草稿 ---\n{draft}\n")

    # 4. 六维写作检查
    print("[2/3] 六维写作检查...")
    report = writing_mod.scan(draft)
    print(f"  通过: {report['passed']} | 问题 {report['total_issues']} | "
          f"fail {report['fail_count']}")
    for i in report["issues"][:8]:
        print(f"    [{i['dim']}/{i['severity']}] {i['msg']}")

    # 5. 提交记忆：主题 + 检查结果
    print("[3/3] 提交记忆...")
    m.add_fact(f"写了推文: {topic}", tags=["写作", "公众号"])
    if not report["passed"]:
        m.add_fact(f"推文「{topic}」D5需改进(去AI味)", tags=["写作", "待改"])
        print("  (已记录待改进项)")
    else:
        print("  (推文通过六维检查)")

    print("\n== 完成：一人公司写推文全流程 ==")
    return report


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "本体驱动的知识管理"
    main(topic)
