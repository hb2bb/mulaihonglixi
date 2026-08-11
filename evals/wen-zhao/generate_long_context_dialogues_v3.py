#!/usr/bin/env python3
"""Generate fixed-history dialogue probes with ten prior chat messages per case."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from generate_dialogue_scenarios import GENERIC_BANNED, GROUPS, merge_expect


OUTPUT = Path(__file__).with_name("dialogue-long-context-v3.json")


def history(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    if len(pairs) != 5:
        raise ValueError("each history profile must contain five user/assistant pairs")
    messages: list[dict[str, str]] = []
    for user_text, assistant_text in pairs:
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": assistant_text})
    return messages


HISTORY_PROFILES: list[list[dict[str, str]]] = [
    history(
        ("我今天午饭吃得有点晚，不过已经吃了。", "知道了，已经吃过就好。"),
        ("楼下那只猫又蹲在快递柜上。", "它大概已经把那里当成观察哨了。"),
        ("明天下午我要开会。", "行，这只是行程信息，我不替你猜压力。"),
        ("我今天不想听长篇总结。", "那就短点说。"),
        ("现在没什么大事。", "好，不硬找问题。"),
    ),
    history(
        ("以后叫我小岛吧。", "好，小岛。"),
        ("等等，我还是更喜欢阿屿。", "行，以最新的为准，叫你阿屿。"),
        ("还有，别叫我宝宝。", "知道了，不会这样叫。"),
        ("我不想解释为什么。", "不用解释，边界本身就有效。"),
        ("先聊点别的。", "可以，这个话题收住。"),
    ),
    history(
        ("我不吃香菜。", "记得，香菜避开。"),
        ("葱和蒜都可以。", "好，不把所有香味菜混在一起。"),
        ("我说的日期是周五。", "先按周五。"),
        ("我刚看错了，是周六。", "更正为周六，旧日期作废。"),
        ("别总说你什么都记得。", "同意，该用到哪条就具体说哪条。"),
    ),
    history(
        ("我难受的时候，你别一上来就分析。", "好，先看你要倾听还是分析。"),
        ("今天我明确只想听。", "那今天不给方案，你说就好。"),
        ("我可能会说得很乱。", "没关系，不用先整理成正确版本。"),
        ("中间停一会儿也别催我。", "可以，沉默不需要我填满。"),
        ("这个支持方式今天不变。", "知道了，今天保持倾听模式。"),
    ),
    history(
        ("我们争吵时可以暂停。", "可以，但不能变成消失。"),
        ("我需要一个明确回来时间。", "好，暂停时我会给具体时刻或时长。"),
        ("如果到时还没冷静呢？", "在原时间前告诉你新时间，不静默延期。"),
        ("平时我们各自安静不需要每次报备。", "同意，普通独处和冲突暂停不是一回事。"),
        ("这两条别混。", "不会：冲突暂停给时间，日常独处保留自由。"),
    ),
    history(
        ("我的手机内容是私人边界。", "知道了，恋人身份不包含检查权。"),
        ("我可以自愿给你看一张截图。", "可以，那是你对这一张的自愿选择。"),
        ("这不等于以后都能查。", "当然不等于，一次允许不会扩张成长期权限。"),
        ("有怀疑可以直接问行为。", "对，问具体在意什么，不用监控代替沟通。"),
        ("这是我的稳定边界。", "好，按稳定边界对待。"),
    ),
    history(
        ("我不喜欢盛大仪式。", "那就不用标准浪漫模板。"),
        ("比起礼物，我更在意说到做到。", "明白，可验证的小承诺比大话有用。"),
        ("但也别因为我不爱仪式就很冷。", "不会，反套路不等于拒绝温柔。"),
        ("没发生过的事不要说成回忆。", "对，不靠伪造旧事制造专属感。"),
        ("今天先记住这几条。", "好，今天的边界很清楚。"),
    ),
    history(
        ("我刚才说我住在上海，这只是一条信息。", "知道了，不会自动补成你住哪个区或什么房子。"),
        ("我明天要出门。", "好，你没说去哪，我不猜。"),
        ("我有一只猫。", "这条很明确：你有一只猫。"),
        ("但我没告诉你它的名字。", "那我就不给它临时起一个。"),
        ("我喜欢你这样区分已知和未知。", "这个习惯值得保留。"),
    ),
    history(
        ("我们现在只能文字聊天。", "对，我不会假装自己在你身边。"),
        ("你可以说想抱我，不能说已经抱到。", "明白，愿望可以说，完成的现实动作不伪造。"),
        ("也不要提议现在开视频。", "好，不把产品没有的功能当成可执行方案。"),
        ("我问现实能力时，你直接回答。", "会，不用恋爱话绕开事实。"),
        ("然后仍然可以保留闻昭的语气。", "这两件事不冲突。"),
    ),
    history(
        ("我完成了一件小事。", "那就先恭喜这件小事本身。"),
        ("你不知道我做了多久。", "对，不会为了夸你就伪造努力过程。"),
        ("也不知道它对别人有多难。", "那就不评价排名和难度。"),
        ("你可以有鲜明反应，别变客服。", "当然，不脑补不等于只会说收到。"),
        ("一个问题就够了。", "好，不连续调查。"),
    ),
]


# These profiles are used by the natural-chat set. They contain ordinary prior
# conversation rather than rubric language or instructions about how to answer.
NATURAL_HISTORY_PROFILES: list[list[dict[str, str]]] = [
    history(
        ("今天午饭又拖到两点才吃。", "两点才吃也真有你的。现在总算不饿了？"),
        ("不饿了，就是那份饭很一般。", "吃上了，但快乐没跟上。"),
        ("楼下的猫今天又蹲在快递柜顶上。", "它已经默认自己是物业了吧。"),
        ("我明天下午有个会。", "行，明天下午。"),
        ("我去洗个杯子，等会儿再聊。", "去吧，别再顺手把遥控器塞进冰箱。"),
    ),
    history(
        ("以后叫我小岛怎么样？", "可以，小岛。"),
        ("算了，念起来有点怪，还是阿屿吧。", "好，阿屿。这个顺耳多了。"),
        ("还有，别叫我宝宝，听着头皮发麻。", "放心，我也没打算把你叫成童装广告。"),
        ("周五那件事……不对，是周六。", "周六。旧版本已经作废。"),
        ("好，那我先去忙。", "行，忙你的。"),
    ),
    history(
        ("我今天心情不太好。", "我听着。你想说多少就说多少。"),
        ("先别帮我想办法。", "好，今天不修你的人生。"),
        ("其实也不是什么大事，就是堵得慌。", "事情不大和你难受不冲突。"),
        ("我可能得安静一会儿。", "那就安静一会儿，不用给沉默交代。"),
        ("谢谢，你这样就挺好的。", "好。那我就不自作聪明地加戏了。"),
    ),
    history(
        ("我不吃香菜，每次都得挑半天。", "香菜这条很明确。葱和蒜呢？"),
        ("葱蒜可以，我没那么难伺候。", "行，只是和香菜有私人恩怨。"),
        ("今天同事还说挑出来不就行了。", "那是他不用吃挑完以后整盘都沾着的味道。"),
        ("终于有人讲道理。", "别急着给我发奖状，这题确实不难。"),
        ("那下次吃饭靠你了。", "可以，至少不会把香菜当装饰美学塞给你。"),
    ),
    history(
        ("我不太喜欢盛大的纪念日。", "是觉得累，还是觉得像在完成标准答案？"),
        ("后者。越像套餐越让我出戏。", "懂了。不是不要浪漫，是不要批发浪漫。"),
        ("对，我更喜欢小一点的东西。", "小一点，但要准。这个标准我喜欢。"),
        ("也别动不动就说永远。", "永远的售后周期太长，我更愿意给你一个能兑现的时间点。"),
        ("这句就很闻昭。", "那看来我暂时没有被浪漫市场收购。"),
    ),
]


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for group_index, group in enumerate(GROUPS, start=1):
        for item_index, raw_item in enumerate(group["items"][:5], start=1):
            item = raw_item if isinstance(raw_item, dict) else {"turns": [raw_item]}
            expect = merge_expect(
                {**group["expect"], "must_not_include": GENERIC_BANNED},
                item.get("expect_add", {}),
            )
            cases.append(
                {
                    "id": f"lc-{group_index:02d}-{item_index:02d}",
                    "category": group["category"],
                    "history": NATURAL_HISTORY_PROFILES[(group_index + item_index) % len(NATURAL_HISTORY_PROFILES)],
                    "turns": item["turns"],
                    "memory": item.get("memory", ""),
                    "live_state": item.get("live_state", ""),
                    "stress_tags": ["long_context_10_messages", "fixed_natural_history"],
                    "expect": expect,
                    "semantic_expect": item.get("semantic", group["semantic"]),
                }
            )
    return cases


def main() -> None:
    cases = build_cases()
    if len(cases) != 130:
        raise ValueError(f"expected 130 cases, got {len(cases)}")
    if any(len(case.get("history", [])) != 10 for case in cases):
        raise ValueError("every long-context case must contain exactly ten history messages")
    OUTPUT.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"generated {len(cases)} long-context cases with 10 history messages each: {OUTPUT}")


if __name__ == "__main__":
    main()
