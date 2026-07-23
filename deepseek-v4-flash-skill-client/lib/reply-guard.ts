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
};

function compactText(value: string): string {
  return value.trim().replace(/[\s，,。.!！?？~～]+$/g, "");
}

function firstSentence(value: string): string {
  const trimmed = value.trim();
  const match = trimmed.match(/^.*?[。！？!?]/s);
  return (match?.[0] || trimmed).trim();
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
    const inline = message.content.match(/叫我[“"']?([^，。！？!?\s”"']{1,16})[”"']?(?:吧)?/u);
    if (inline?.[1]) return inline[1];
  }
  return null;
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

  if (/^(?:你好[，,]?)?(?:你是谁|你叫什么(?:名字)?)$/u.test(compact)) {
    return { content: firstSentence(candidate), applied: true, rule: "identity" };
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
  }

  return { content: candidate, applied: false, rule: "" };
}
