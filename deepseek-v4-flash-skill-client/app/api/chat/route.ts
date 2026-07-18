import { NextRequest, NextResponse } from "next/server";
import { SKILL_BUNDLE } from "@/lib/skill-bundle.generated";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const MAX_MESSAGES = 30;
const MAX_MESSAGE_LENGTH = 12_000;
const MAX_TOTAL_LENGTH = 60_000;

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

export async function POST(request: NextRequest) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "服务尚未配置 DeepSeek API Key。" },
      { status: 503 },
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
  const model = process.env.DEEPSEEK_MODEL || "deepseek-v4-flash";

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
          {
            role: "system",
            content: "你是一个可靠的代码助手。回答应清晰、准确，并优先提供可运行的代码。",
          },
          // 每一次上游调用都加入完整 Skill，而不是依赖浏览器保存的隐藏状态。
          { role: "system", content: SKILL_BUNDLE },
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
