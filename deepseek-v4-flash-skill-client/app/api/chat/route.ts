import { NextRequest, NextResponse } from "next/server";
import { SKILL_BUNDLE } from "@/lib/skill-bundle.generated";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const MAX_MESSAGES = 200;
const MAX_MESSAGE_LENGTH = 12_000;
const MAX_TOTAL_LENGTH = 60_000;
const RATE_LIMIT = 10;
const RATE_LIMIT_WINDOW_MS = 60_000;

const PERSONA_SYSTEM_PROMPT =
  "请遵守随后提供的项目 Skill 进行自然中文对话。不要用通用代码助手口吻覆盖角色规则；只有用户明确暂停角色或切换助手模式时，才使用普通助手口吻。";

const WEB_RUNTIME_PROMPT = [
  "这是无文件写入能力的网页聊天运行时。Skill bundle 中的 relationship-memory.md 是本次构建时的只读快照。",
  "不得声称已经修改、保存或写入记忆文件；当前页面内的上下文只由随后提供的 messages 维持。",
  "用户当前消息中的更正和边界高于较早的聊天内容。发送前必须执行 Skill 中的硬过滤规则。",
].join("\n");

const globalRateLimit = globalThis as typeof globalThis & {
  flashLabRequests?: Map<string, number[]>;
};
const requestRecords = (globalRateLimit.flashLabRequests ??= new Map());

function clientIdentity(request: NextRequest) {
  return (
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown"
  );
}

function allowRequest(identity: string) {
  const now = Date.now();
  const recent = (requestRecords.get(identity) || []).filter(
    (timestamp) => now - timestamp < RATE_LIMIT_WINDOW_MS,
  );
  if (recent.length >= RATE_LIMIT) {
    requestRecords.set(identity, recent);
    return false;
  }
  recent.push(now);
  requestRecords.set(identity, recent);
  return true;
}

function safeEqual(left: string, right: string) {
  const length = Math.max(left.length, right.length);
  let different = left.length ^ right.length;
  for (let index = 0; index < length; index += 1) {
    different |= (left.charCodeAt(index) || 0) ^ (right.charCodeAt(index) || 0);
  }
  return different === 0;
}

function validateMessages(value: unknown): ChatMessage[] | null {
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_MESSAGES) {
    return null;
  }
  let totalLength = 0;
  const messages: ChatMessage[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return null;
    const { role, content } = item as Record<string, unknown>;
    if (role !== "user" && role !== "assistant") return null;
    if (typeof content !== "string" || !content.trim() || content.length > MAX_MESSAGE_LENGTH) {
      return null;
    }
    totalLength += content.length;
    if (totalLength > MAX_TOTAL_LENGTH) return null;
    messages.push({ role, content });
  }
  return messages;
}

export async function GET() {
  return NextResponse.json({
    ready: Boolean(process.env.DEEPSEEK_API_KEY),
    access_key_required: Boolean(process.env.SITE_ACCESS_KEY),
  });
}

export async function POST(request: NextRequest) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "服务尚未配置 DeepSeek API Key。" },
      { status: 503 },
    );
  }

  const accessKey = process.env.SITE_ACCESS_KEY;
  if (
    accessKey &&
    !safeEqual(request.headers.get("X-Flash-Lab-Access") || "", accessKey)
  ) {
    return NextResponse.json({ error: "体验访问码不正确。" }, { status: 401 });
  }

  if (!allowRequest(clientIdentity(request))) {
    return NextResponse.json(
      { error: "请求过于频繁，请稍后再试。" },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "请求不是有效的 JSON。" }, { status: 400 });
  }
  const messages = validateMessages((body as { messages?: unknown })?.messages);
  if (!messages) {
    return NextResponse.json({ error: "对话内容为空、过长或格式不正确。" }, { status: 400 });
  }

  const baseUrl = (process.env.DEEPSEEK_BASE_URL || "https://api.deepseek.com").replace(
    /\/$/,
    "",
  );
  const model = process.env.DEEPSEEK_MODEL || "deepseek-v4-pro";

  try {
    const upstream = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: PERSONA_SYSTEM_PROMPT },
          // 每一次上游调用都加入完整 Skill，而不是依赖浏览器保存的隐藏状态。
          { role: "system", content: SKILL_BUNDLE },
          // 网页端没有工具和可写文件系统，明确覆盖 Skill 中不适用于该运行时的记忆写入步骤。
          { role: "system", content: WEB_RUNTIME_PROMPT },
          ...messages,
        ],
        stream: false,
        thinking: { type: "enabled" },
        reasoning_effort: "high",
        max_tokens: 8_192,
      }),
    });

    if (!upstream.ok) {
      // 不把上游响应体返回给访客，避免意外泄露服务端信息。
      console.error("DeepSeek upstream error", upstream.status, await upstream.text());
      return NextResponse.json(
        { error: `模型服务暂时不可用（${upstream.status}）。` },
        { status: 502 },
      );
    }

    const result = (await upstream.json()) as {
      choices?: Array<{ message?: { content?: unknown } }>;
    };
    const content = result.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      return NextResponse.json({ error: "模型没有返回有效文本。" }, { status: 502 });
    }
    return NextResponse.json({ content });
  } catch (error) {
    console.error("DeepSeek request failed", error);
    return NextResponse.json({ error: "连接模型服务失败，请稍后重试。" }, { status: 502 });
  }
}
