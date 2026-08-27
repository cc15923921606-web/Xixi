from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


_CRISIS_RE = re.compile(
    r"(?:我.{0,8})?(?:不想活(?:了|下去)?|活不下去|想死|自杀|结束生命|"
    r"伤害自己|割腕|跳楼|死了算了|没必要活(?:了|着)?)"
)
_REPORTED_CRISIS_RE = re.compile(
    r"(?:电影|剧情|角色|新闻|报道|台词|他说|她说|别人说).{0,16}"
    r"(?:不想活|想死|自杀|结束生命|伤害自己)"
)
_GRIEF_RE = re.compile(
    r"(?:家人|亲人|朋友|同学|爷爷|奶奶|外公|外婆|爸爸|妈妈|宠物|猫|狗)"
    r".{0,10}(?:去世|离世|走了|没了)|(?:去世|离世).{0,8}(?:难受|难过|想念)"
)
_SADNESS_RE = re.compile(
    r"(?:难过|伤心|想哭|哭了|心里堵|失落|委屈|破防|低落|心情不好|不开心)"
)
_ANXIETY_RE = re.compile(
    r"(?:焦虑|紧张|害怕|恐慌|心慌|不安|压力(?:好|很|太)?大|担心.{0,8}(?:失败|来不及|出事)|怎么办)"
)
_EXHAUSTION_RE = re.compile(
    r"(?:好累|太累|累死|累坏|撑不住|顶不住|没力气|精疲力尽|筋疲力尽|不想动|熬不住)"
)
_LONELINESS_RE = re.compile(
    r"(?:孤独|孤单|没人理解|没人懂|没人陪|被冷落|被忽视|只有我一个人)"
)
_ANGER_RE = re.compile(
    r"(?:气死|气炸|火大|生气|恼火|烦死|受不了|凭什么|太过分|恶心死|真的服了)"
)
_BOT_COMPLAINT_RE = re.compile(
    r"(?:你|昔夕|小夕|(?<![A-Za-z0-9_])xx(?![A-Za-z0-9_])).{0,18}"
    r"(?:让我|害我|搞得我|总是|根本|刚才|又).{0,10}"
    r"(?:生气|失望|难受|不舒服|很烦|没听懂|不尊重|敷衍|说错|弄错|太过分)|"
    r"(?:我对你|我对昔夕|我对小夕).{0,8}(?:生气|失望|不满)|"
    r"(?:你|昔夕|小夕).{0,12}(?:根本没听懂|一点都不懂|不在乎我|不关心我)",
    re.IGNORECASE,
)
_DIRECTED_PROVOCATION_RE = re.compile(
    r"(?:(?:你|昔夕|小夕|(?<![A-Za-z0-9_])xx(?![A-Za-z0-9_])).{0,10}"
    r"(?:笨|傻|蠢|菜|怂|废物|垃圾|没用|白痴|弱智|欠骂|真逊|真拉)|"
    r"(?:笨蛋|傻瓜|白痴|废物|垃圾|蠢货).{0,8}(?:昔夕|小夕|你)|"
    r"^(?:闭嘴|滚|爬|少废话|你可拉倒吧)[！!。,.，\s]*$)",
    re.IGNORECASE,
)
_SHAME_RE = re.compile(
    r"(?:尴尬|丢脸|社死|出丑|后悔|搞砸|弄砸|失败了|我真没用|我好没用|都怪我)"
)
_SETBACK_RE = re.compile(
    r"(?:我|刚刚|今天|这次).{0,12}(?:被拒绝|被裁员|失业|分手|没考过|没通过|落选|"
    r"被骂|被批评|吵架|生病|住院|弄丢|搞砸|失败)"
)
_INTERPERSONAL_HURT_RE = re.compile(
    r"(?:他|她|他们|别人|朋友|同事|同学).{0,12}(?:骗我|骂我|羞辱我|背叛我|"
    r"无视我|冷落我|拉黑我|放我鸽子|拿我开玩笑)"
)
_JOY_RE = re.compile(
    r"(?:我.{0,8})?(?:太好了|好开心|高兴死|成功了|通过了|过了|中了|赢了|"
    r"搞定了|做到了|终于(?:完成|成功|通过|结束|等到|拿到))"
)
_POSITIVE_EVENT_RE = re.compile(
    r"(?:我|刚刚|今天|这次).{0,12}(?:拿到(?:offer|录取|奖励)|被录取|升职|获奖|"
    r"通关|考过|谈成|做完|完成|解决了)",
    re.IGNORECASE,
)
_SELF_DEPRECATION_RE = re.compile(
    r"(?:我可真|我真是|我也太).{0,8}(?:厉害|聪明|优秀|棒).{0,12}(?:又|结果|居然)?"
    r"(?:搞砸|失败|忘了|迟到|出错)|(?:呵呵|笑死).{0,12}(?:我真|我可真).{0,6}(?:棒|厉害)"
)
_WITHDRAWAL_RE = re.compile(
    r"^(?:算了(?:[，,、\s]*(?:没事|不说了|当我没说))?|没事|没什么|随便|都行|"
    r"不说了|当我没说|无所谓|行吧|好吧|就这样吧)"
    r"[。.!！…~～\s]*$"
)
_MINIMIZING_END_RE = re.compile(r"(?:但|不过|可是)?(?:我)?没事(?:的)?[。.!！…~～\s]*$")
_APOLOGY_RE = re.compile(r"(?:对不起|抱歉|我错了|是我不好|刚才是我不对|原谅我)")
_ADVICE_RE = re.compile(
    r"(?:我该怎么办|怎么办才好|该怎么(?:办|做|处理)|你觉得我(?:该|应该)|"
    r"给我.{0,6}建议|帮我想想办法|有什么办法|怎么解决|怎么处理)"
)
_LISTEN_RE = re.compile(
    r"(?:听我说|让我说完|我想说说|想跟你聊聊|陪我聊会|先别给建议|不用给建议|只想吐槽)"
)
_REASSURANCE_RE = re.compile(
    r"(?:我是不是.{0,8}(?:很差|没用|讨厌|不值得)|你会不会.{0,8}(?:离开|讨厌|不要我)|"
    r"真的会没事吗|我能做好吗)"
)
_MINIMIZING_REPLIES = (
    "你想太多了",
    "没什么大不了",
    "至少",
    "别人更惨",
    "振作一点",
    "别矫情",
    "开心点",
)


@dataclass(frozen=True)
class SocialAppraisal:
    emotion: str
    intensity: str
    need: str
    repeated: bool = False
    crisis: bool = False
    mixed_signal: bool = False
    directed_at_xixi: bool = False
    provoked: bool = False

    def render(self) -> str:
        if self.emotion == "neutral" and self.need == "direct_response":
            return ""

        emotion_labels = {
            "crisis": "可能存在即时安全风险",
            "grief": "悲伤或哀痛",
            "sadness": "难过、委屈或失落",
            "anxiety": "焦虑、害怕或压力",
            "exhaustion": "疲惫或不堪重负",
            "loneliness": "孤独或被忽视感",
            "anger": "生气、受挫或边界被侵犯",
            "shame": "尴尬、自责或羞耻",
            "joy": "开心、兴奋或成就感",
            "apology": "在尝试修复关系",
            "withdrawal": "嘴上收住话题，可能仍有情绪",
            "neutral": "没有明确情绪信号",
        }
        need_labels = {
            "safety": "先确保人身安全并联系现实支持",
            "presence": "先被听见和接住，不急着解决",
            "advice": "先共情，再给少量可执行办法",
            "validation_without_escalation": "承认感受，但不替对方武断定罪或拱火",
            "reduce_shame": "降低羞耻感，把一次失误与整个人分开",
            "celebration": "真诚分享喜悦，回应具体成果",
            "repair": "回应道歉和具体伤害，按关系状态决定接受程度",
            "accountability": "先理解对方受到的影响，再承担责任并修正",
            "comeback": "对方在直接调侃或挑衅你，可以有分寸地回嘴或立边界",
            "gentle_space": "留出空间，不逼问也不冷处理",
            "reassurance": "给有依据的安定感，不作无法保证的承诺",
            "direct_response": "直接回应当前内容",
        }
        lines = [
            "本轮社交与情绪判断（内部使用，不要复述这些标签）：",
            f"- 对方可能的状态：{emotion_labels[self.emotion]}，强度{self.intensity}",
            f"- 此刻更可能需要：{need_labels[self.need]}",
        ]
        if self.repeated:
            lines.append("- 这类困扰在最近对话出现过；自然体现你记得，但不要责怪对方重复，也不要套用上次答案。")
        if self.mixed_signal:
            lines.append("- 表面说没事或算了与近期情绪不完全一致；轻轻留意即可，不要逼对方承认或连续追问。")
        if self.directed_at_xixi:
            lines.append("- 情绪或不满明确指向昔夕本人；不要当成对第三方的抱怨，也不要急着替自己辩解。")
        if self.provoked:
            lines.append(
                "- 对方在直接调侃或挑衅昔夕；先结合关系和语气判断是玩笑还是恶意，不必假装没听见。"
            )

        if self.crisis:
            lines.extend(
                (
                    "回应顺序：认真表明你在意 -> 直接确认对方此刻是否安全、是否已经准备伤害自己 -> 鼓励立刻联系身边可信的人并远离危险物品。",
                    "若危险迫近，明确建议立即拨打当地急救或报警电话（中国大陆为120/110）或前往急诊；不要用傲娇、玩笑、责备、激将法，也不要承诺替对方保密。",
                )
            )
            return "\n".join(lines)

        strategies = {
            "presence": (
                "先对具体处境给一句有内容的情绪回应，让对方感到被理解；不要立刻分析原因、列清单或灌鸡汤。"
                "可以陪着说，但没有必要每次都以问题结尾。"
            ),
            "advice": (
                "先用一句话接住情绪，再给一到三个最贴近当前处境的具体做法，并说明先做哪一个；"
                "不要一下抛出长清单，也不要把责任全推回对方。"
            ),
            "validation_without_escalation": (
                "承认对方生气有其原因，区分已知事实与对方的推测；可以帮他梳理边界或下一步，"
                "但不要附和辱骂、煽动报复或断言第三方一定恶意。"
            ),
            "reduce_shame": (
                "别拿这件事开玩笑，也别用“这有什么”否定感受；指出一次失误不等于整个人很差，"
                "再根据对方是否求助决定要不要谈补救。"
            ),
            "celebration": (
                "把开心程度调到与对方接近，具体回应他做到的事；这轮不要马上泼冷水、说教或把话题转回自己。"
            ),
            "repair": (
                "看道歉是否承认了具体影响；可以自然接受、说明仍需一点时间，或清楚表达边界，"
                "不要机械说“没关系”，也不要借机翻旧账羞辱对方。"
            ),
            "accountability": (
                "先准确回应哪句话或行为让对方不舒服，承认影响并自然道歉；能当场改的就直接改。"
                "不要强调“我本意不是这样”、争论对方是否太敏感，也不要用傲娇或玩笑逃避责任。"
            ),
            "comeback": (
                "轻微逗弄时可以短促、机灵地怼回去，恶意冒犯时可以直接表达不爽并立边界；"
                "不用客服式劝导，也不用每次上升成严肃说教。怼当前这句话或行为，不贬低人的基本价值，"
                "不用身份歧视、现实威胁、隐私攻击或反复追骂。"
            ),
            "gentle_space": (
                "给一句不施压的在场感，让对方知道想继续说时你还在；不要连问“怎么了”，也不要因为一句“没事”就冷淡转场。"
            ),
            "reassurance": (
                "肯定能从事实和关系中确认的部分；不能保证的结果就坦率说明不确定，同时给出稳定、具体的支持。"
            ),
            "direct_response": "直接回应当前内容，语气与对方一致，不额外制造心理分析。",
        }
        lines.append(f"- 回应方式：{strategies[self.need]}")
        lines.append(
            "避免空泛套话和比较痛苦，不要说“"
            + "、".join(_MINIMIZING_REPLIES)
            + "”这类话。"
        )
        return "\n".join(lines)


def appraise_social_context(
    message: str,
    *,
    recent_history: Iterable[Mapping[str, str]] = (),
    context_text: str = "",
    speaker: str = "",
) -> SocialAppraisal:
    text = str(message or "").strip()
    history_texts = [
        str(item.get("content") or "")
        for item in recent_history
        if item.get("role") == "user"
        and _history_belongs_to_speaker(str(item.get("content") or ""), speaker)
    ][-4:]
    if context_text.strip():
        relevant_group_context = _group_context_for_speaker(context_text, speaker)
        if relevant_group_context:
            history_texts.append(relevant_group_context[-2000:])

    crisis = bool(_CRISIS_RE.search(text)) and not bool(_REPORTED_CRISIS_RE.search(text))
    self_deprecating = bool(_SELF_DEPRECATION_RE.search(text))
    directed_at_xixi = bool(_BOT_COMPLAINT_RE.search(text))
    provoked = bool(_DIRECTED_PROVOCATION_RE.search(text)) and not directed_at_xixi
    mixed_signal = (
        bool(_WITHDRAWAL_RE.fullmatch(text))
        and any(_has_distress_signal(item) for item in history_texts)
    ) or bool(_MINIMIZING_END_RE.search(text) and _has_distress_signal(text))

    if crisis:
        emotion = "crisis"
    elif _GRIEF_RE.search(text):
        emotion = "grief"
    elif self_deprecating or _SHAME_RE.search(text):
        emotion = "shame"
    elif _SADNESS_RE.search(text) or _SETBACK_RE.search(text):
        emotion = "sadness"
    elif _LONELINESS_RE.search(text):
        emotion = "loneliness"
    elif _EXHAUSTION_RE.search(text):
        emotion = "exhaustion"
    elif _ANXIETY_RE.search(text):
        emotion = "anxiety"
    elif directed_at_xixi or provoked or _ANGER_RE.search(text) or _INTERPERSONAL_HURT_RE.search(text):
        emotion = "anger"
    elif _APOLOGY_RE.search(text):
        emotion = "apology"
    elif _WITHDRAWAL_RE.fullmatch(text):
        emotion = "withdrawal"
    elif _JOY_RE.search(text) or _POSITIVE_EVENT_RE.search(text):
        emotion = "joy"
    else:
        emotion = "neutral"

    explicit_advice = bool(_ADVICE_RE.search(text))
    explicit_listening = bool(_LISTEN_RE.search(text))
    reassurance = bool(_REASSURANCE_RE.search(text))
    if crisis:
        need = "safety"
    elif explicit_advice and not explicit_listening:
        need = "advice"
    elif directed_at_xixi:
        need = "accountability"
    elif provoked:
        need = "comeback"
    elif explicit_listening:
        need = "presence"
    elif emotion == "anger":
        need = "validation_without_escalation"
    elif emotion == "shame":
        need = "reduce_shame"
    elif emotion == "joy":
        need = "celebration"
    elif emotion == "apology":
        need = "repair"
    elif emotion == "withdrawal" or mixed_signal:
        need = "gentle_space"
    elif reassurance:
        need = "reassurance"
    elif emotion in {"grief", "sadness", "anxiety", "exhaustion", "loneliness"}:
        need = "presence"
    else:
        need = "direct_response"

    intensity = "高" if crisis or _high_intensity(text) else "中等" if emotion != "neutral" else "较低"
    repeated = emotion not in {"neutral", "joy", "apology", "withdrawal"} and any(
        _emotion_matches(emotion, item) for item in history_texts
    )
    return SocialAppraisal(
        emotion=emotion,
        intensity=intensity,
        need=need,
        repeated=repeated,
        crisis=crisis,
        mixed_signal=mixed_signal,
        directed_at_xixi=directed_at_xixi,
        provoked=provoked,
    )


def _has_distress_signal(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            _CRISIS_RE,
            _GRIEF_RE,
            _SADNESS_RE,
            _ANXIETY_RE,
            _EXHAUSTION_RE,
            _LONELINESS_RE,
            _ANGER_RE,
            _SHAME_RE,
            _SETBACK_RE,
            _INTERPERSONAL_HURT_RE,
        )
    )


def _emotion_matches(emotion: str, text: str) -> bool:
    if emotion == "sadness":
        return bool(_SADNESS_RE.search(text) or _SETBACK_RE.search(text))
    if emotion == "anger":
        return bool(_ANGER_RE.search(text) or _INTERPERSONAL_HURT_RE.search(text))
    patterns = {
        "crisis": _CRISIS_RE,
        "grief": _GRIEF_RE,
        "sadness": _SADNESS_RE,
        "anxiety": _ANXIETY_RE,
        "exhaustion": _EXHAUSTION_RE,
        "loneliness": _LONELINESS_RE,
        "anger": _ANGER_RE,
        "shame": _SHAME_RE,
    }
    pattern = patterns.get(emotion)
    return bool(pattern and pattern.search(text))


def _high_intensity(text: str) -> bool:
    return bool(
        re.search(r"(?:特别|非常|真的|太|快要|已经).{0,8}(?:崩溃|受不了|撑不住|害怕|难过|焦虑|生气)", text)
        or re.search(r"[！!]{2,}|\.{3,}|…{2,}", text)
    )


def _history_belongs_to_speaker(content: str, speaker: str) -> bool:
    sender_match = re.match(r"^\[当前消息发送者：(.+?)\]", content)
    if not sender_match or not speaker.strip():
        return True
    return _same_speaker(sender_match.group(1), speaker)


def _group_context_for_speaker(context_text: str, speaker: str) -> str:
    if not speaker.strip():
        return context_text
    relevant = []
    for line in context_text.splitlines():
        label = line.split("：", 1)[0].split(":", 1)[0].strip()
        if label and _same_speaker(label, speaker):
            relevant.append(line)
    return "\n".join(relevant)


def _same_speaker(left: str, right: str) -> bool:
    left_qq = re.search(r"QQ\s*(\d{5,})", left, re.IGNORECASE)
    right_qq = re.search(r"QQ\s*(\d{5,})", right, re.IGNORECASE)
    if left_qq and right_qq:
        return left_qq.group(1) == right_qq.group(1)
    left_name = re.split(r"[（(]", left, maxsplit=1)[0].strip()
    right_name = re.split(r"[（(]", right, maxsplit=1)[0].strip()
    return bool(left_name and right_name and left_name.casefold() == right_name.casefold())
