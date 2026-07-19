import { NextRequest, NextResponse } from "next/server";
import { RUNTIME_TEXT } from "@/lib/skill-bundle.generated";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const MAX_MESSAGES = 10;
const MAX_MESSAGE_LENGTH = 12_000;
const MAX_TOTAL_LENGTH = 30_000;
const MAX_MEMORY_LENGTH = 4_000;
const MAX_MEMORY_ITEMS = 12;
const RATE_LIMIT = 4;
const RATE_LIMIT_WINDOW_MS = 60_000;

const globalRateLimit = globalThis as typeof globalThis & {
  flashLabMemoryRequests?: Map<string, number[]>;
};
const requestRecords = (globalRateLimit.flashLabMemoryRequests ??= new Map());

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
  if (!Array.isArray(value) || value.length === 0 || value.length > MAX_MESSAGES) return null;
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

function normalizeMemory(value: unknown): string | null {
  if (value === undefined || value === "") return "";
  if (typeof value !== "string" || value.length > MAX_MEMORY_LENGTH) return null;
  const items = value
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^[-*]\s*/, ""))
    .filter(Boolean)
    .slice(0, MAX_MEMORY_ITEMS)
    .map((line) => `- ${line.slice(0, 300)}`);
  const normalized = items.join("\n");
  return normalized.length <= MAX_MEMORY_LENGTH ? normalized : normalized.slice(0, MAX_MEMORY_LENGTH);
}

function parseMemoryResponse(content: string): string | null {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const parsed = JSON.parse(content.slice(start, end + 1)) as { memory?: unknown };
    return normalizeMemory(parsed.memory);
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "服务尚未配置 DeepSeek API Key。" }, { status: 503 });
  }

  const accessKey = process.env.SITE_ACCESS_KEY;
  if (accessKey && !safeEqual(request.headers.get("X-Flash-Lab-Access") || "", accessKey)) {
    return NextResponse.json({ error: "体验访问码不正确。" }, { status: 401 });
  }
  if (!allowRequest(clientIdentity(request))) {
    return NextResponse.json(
      { error: "记忆整理请求过于频繁，请稍后再试。" },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "请求不是有效的 JSON。" }, { status: 400 });
  }
  const requestBody = body as { messages?: unknown; memory?: unknown };
  const messages = validateMessages(requestBody?.messages);
  const existingMemory = normalizeMemory(requestBody?.memory);
  if (!messages || existingMemory === null) {
    return NextResponse.json({ error: "记忆整理内容为空、过长或格式不正确。" }, { status: 400 });
  }

  const baseUrl = (process.env.DEEPSEEK_BASE_URL || "https://api.deepseek.com").replace(/\/$/, "");
  const model = process.env.DEEPSEEK_MEMORY_MODEL || process.env.DEEPSEEK_MODEL || "deepseek-v4-pro";

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
          { role: "system", content: RUNTIME_TEXT.memory_system_prompt },
          {
            role: "user",
            content: JSON.stringify({ existing_memory: existingMemory, conversation: messages }),
          },
        ],
        stream: false,
        thinking: { type: "enabled" },
        reasoning_effort: "high",
        max_tokens: 1_200,
      }),
    });
    if (!upstream.ok) {
      console.error("DeepSeek memory upstream error", upstream.status, await upstream.text());
      return NextResponse.json({ error: "记忆整理服务暂时不可用。" }, { status: 502 });
    }
    const result = (await upstream.json()) as {
      choices?: Array<{ message?: { content?: unknown } }>;
    };
    const content = result.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      return NextResponse.json({ error: "记忆模型没有返回有效文本。" }, { status: 502 });
    }
    const memory = parseMemoryResponse(content);
    if (memory === null) {
      return NextResponse.json({ error: "记忆模型返回格式不正确。" }, { status: 502 });
    }
    return NextResponse.json({
      memory,
      debug: { model, output: content },
    });
  } catch (error) {
    console.error("DeepSeek memory request failed", error);
    return NextResponse.json({ error: "连接记忆整理服务失败。" }, { status: 502 });
  }
}
