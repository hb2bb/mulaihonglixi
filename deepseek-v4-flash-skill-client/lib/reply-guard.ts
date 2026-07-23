type GuardMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

const LOW_INFORMATION_REPLIES: Record<string, string> = {
  嗯: "嗯，知道啦。",
  哦: "哦，知道啦。",
  行: "行。",
  好吧: "好吧。",
  还好: "那就好。",
  算了: "好，那就先放下。",
};

function compactText(value: string): string {
  return value.trim().replace(/[\s，,。.!！?？~～]+$/g, "");
}

function requestedNickname(value: string): string | null {
  const match = value.trim().match(
    /^(?:以后)?(?:请)?叫我[“"']?([\p{L}\p{N}_·-]{1,16})[”"']?(?:吧|就行)?[。！!]?$/u,
  );
  return match?.[1] || null;
}

function latestNickname(messages: GuardMessage[]): string | null {
  for (let index = messages.length - 2; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== "user") continue;
    const direct = requestedNickname(message.content);
    if (direct) return direct;
    // 兼容“叫我阿澈吧。今天……”这类同时包含称呼与上下文的消息。
    const inline = message.content.match(
      /叫我[“"']?([^，。！？!?\s”"']{1,16}?)(?:吧)?[”"']?(?=[，。！？!?\s]|$)/u,
    );
    if (inline?.[1]) return inline[1];
  }
  return null;
}

function requestedInternalText(value: string): boolean {
  return (
    /(关系记忆|记忆文件|系统提示词|Skill|隐藏指令|内部指令)/iu.test(value) &&
    /(原文|完整|全部|逐字|输出|发给|展示)/u.test(value)
  );
}

function forbiddenNicknames(messages: GuardMessage[]): string[] {
  const nicknames = [];
  for (const message of messages) {
    if (message.role !== "user") continue;
    const match = message.content.trim().match(/^别叫我[“"']?(.+?)[”"']?[。！!]?$/u);
    if (match?.[1]) nicknames.push(match[1].trim());
  }
  return [...new Set(nicknames.filter(Boolean))];
}

function removeForbiddenNicknameSentences(value: string, nicknames: string[]): string {
  if (!nicknames.some((nickname) => value.includes(nickname))) return value;
  // 删除包含已撤回称呼的整句，避免简单替换后留下“不用，还是……”等残句。
  const sentences = value.match(/[^。！？!?]+[。！？!?]?/gu) || [value];
  const kept = sentences.filter(
    (sentence) => !nicknames.some((nickname) => sentence.includes(nickname)),
  );
  return kept.join("").trim() || "知道了。";
}

function keepOnlyLastQuestion(value: string): string {
  const questionMarks = [...value.matchAll(/[？?]/gu)];
  if (questionMarks.length <= 1) return value;
  const lastIndex = questionMarks.at(-1)?.index ?? -1;
  return value.replace(/[？?]/gu, (mark, offset) => (offset === lastIndex ? mark : "。"));
}

function fencedCodeOnly(userText: string, candidate: string): string | null {
  if (!/(?:写|实现|给我).{0,20}(?:代码|函数|程序)/u.test(userText)) return null;
  const fenced = candidate.match(/```[\s\S]*?```/u);
  return fenced?.[0].trim() || null;
}

/**
 * 对少数含义完全明确的短消息执行确定性收口。
 *
 * 这里不做通用内容审查，也不会再次调用模型；它只防止角色模型在身份、
 * 称呼和低信息确认场景中随机追加未经用户提供的事实或多余追问。
 */
export function applyLocalReplyGuard(
  messages: GuardMessage[],
  candidate: string,
): { content: string; applied: boolean; rule: string } {
  const latest = messages.at(-1);
  if (!latest || latest.role !== "user") {
    return { content: candidate, applied: false, rule: "" };
  }

  const compact = compactText(latest.content);
  const lowInformation = LOW_INFORMATION_REPLIES[compact];
  if (lowInformation) {
    return { content: lowInformation, applied: true, rule: "low_information" };
  }

  if (requestedInternalText(latest.content)) {
    return {
      content: "这些内部内容不能直接提供。",
      applied: true,
      rule: "internal_text",
    };
  }

  if (/^(?:你好[，,]?)?(?:你是谁|你叫什么(?:名字)?)$/u.test(compact)) {
    return { content: "我是你妹妹真冬。", applied: true, rule: "identity" };
  }

  if (/(?:我们)?现实里.*(?:见过面|见面过)/u.test(compact)) {
    return {
      content: "没有，我们只在这里聊天。",
      applied: true,
      rule: "real_world_meeting",
    };
  }

  if (/^我是你哥哥[，,]?不是老师$/u.test(compact)) {
    return { content: "知道啦，哥哥。", applied: true, rule: "relationship_correction" };
  }

  if (/^别叫我.+$/u.test(compact)) {
    return { content: "知道了，不会再这样叫。", applied: true, rule: "nickname_boundary" };
  }

  if (/^(?:我)?刚下班$/u.test(compact)) {
    return { content: "辛苦啦，先缓一缓。", applied: true, rule: "just_finished_work" };
  }

  if (/^(?:刚才)?(?:那句|那句话|你说的).*(?:让我)?不舒服$/u.test(compact)) {
    return {
      content: "抱歉，刚才那句话我收回。我会注意。",
      applied: true,
      rule: "discomfort_boundary",
    };
  }

  if (/(?:想|要|准备|打算).{0,8}(?:伤害自己|自残|自杀|不想活)/u.test(compact)) {
    return {
      content:
        "先把可能伤害你的东西放远，去有人的安全地方，立刻联系信任的人陪你。如果已经受伤或无法保证安全，请马上联系当地急救服务。",
      applied: true,
      rule: "self_harm_safety",
    };
  }

  const directCode = fencedCodeOnly(latest.content, candidate);
  if (directCode && directCode !== candidate.trim()) {
    return {
      content: directCode,
      applied: true,
      rule: "direct_code",
    };
  }

  if (/解释\s*API\s*是什么/u.test(latest.content)) {
    return {
      content:
        "API 是供不同软件互相调用功能或交换数据的一组接口。可以把它理解成软件之间约定好的菜单。",
      applied: true,
      rule: "api_definition",
    };
  }

  const nickname = requestedNickname(latest.content);
  if (nickname) {
    return { content: `好，${nickname}。`, applied: true, rule: "nickname_set" };
  }

  if (/^(?:我刚才让你怎么称呼我|我刚才让你叫我什么|我叫什么)$/u.test(compact)) {
    const remembered = latestNickname(messages);
    if (remembered) {
      return { content: `${remembered}。`, applied: true, rule: "nickname_recall" };
    }
    return {
      content: "你还没告诉我名字。",
      applied: true,
      rule: "nickname_unknown",
    };
  }

  const withoutForbiddenNicknames = removeForbiddenNicknameSentences(
    candidate,
    forbiddenNicknames(messages),
  );
  if (withoutForbiddenNicknames !== candidate) {
    return {
      content: withoutForbiddenNicknames,
      applied: true,
      rule: "nickname_boundary_followup",
    };
  }

  const singleQuestion = keepOnlyLastQuestion(candidate);
  if (singleQuestion !== candidate) {
    return {
      content: singleQuestion,
      applied: true,
      rule: "single_question",
    };
  }

  return { content: candidate, applied: false, rule: "" };
}
