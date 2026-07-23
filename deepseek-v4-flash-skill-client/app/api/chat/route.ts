import { NextRequest, NextResponse } from "next/server";
import { RUNTIME_TEXT, SKILL_BUNDLE } from "@/lib/skill-bundle.generated";
import {
  CHAT_REQUEST_TIMEOUT_MS,
  ModelUpstreamError,
  publicModelFailure,
} from "@/lib/model-api-error";
import { applyLocalReplyGuard } from "@/lib/reply-guard";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const MAX_MESSAGES = 200;
const MAX_MESSAGE_LENGTH = 12_000;
const MAX_TOTAL_LENGTH = 60_000;
const MAX_SESSION_MEMORY_LENGTH = 4_000;
const MAX_LIVE_STATE_LENGTH = 3_000;
const RATE_LIMIT = 10;
const RATE_LIMIT_WINDOW_MS = 60_000;
const MAX_REVIEW_RETRIES = 2;

type ReviewResult = {
  approved: boolean;
  problems: string;
  raw: string;
};

function renderRuntimeText(template: string, values: Record<string, string>) {
  return Object.entries(values).reduce(
    (rendered, [key, value]) => rendered.split(`{${key}}`).join(value),
    template,
  );
}

const globalRateLimit = globalThis as typeof globalThis & {
  flashLabRequests?: Map<string, number[]>;
};
const requestRecords: Map<string, number[]> = (
  globalRateLimit.flashLabRequests ??= new Map<string, number[]>()
);

function envFlag(value: string | undefined, defaultValue = false) {
  if (value === undefined) return defaultValue;
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

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

function validateSessionMemory(value: unknown): string | null {
  if (value === undefined || value === "") return "";
  if (typeof value !== "string" || value.length > MAX_SESSION_MEMORY_LENGTH) return null;
  return value.trim();
}

function validateLiveState(value: unknown): string | null {
  if (value === undefined || value === "") return "";
  if (typeof value !== "string" || value.length > MAX_LIVE_STATE_LENGTH) return null;
  return value.trim();
}

function extractJsonObject(content: string): Record<string, unknown> | null {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const value = JSON.parse(content.slice(start, end + 1));
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

async function callCompatibleModel(
  baseUrl: string,
  apiKey: string,
  model: string,
  messages: Array<{ role: "system" | "user" | "assistant"; content: string }>,
  maxTokens: number,
) {
  const upstream = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ model, messages, stream: false, max_tokens: maxTokens }),
    signal: AbortSignal.timeout(CHAT_REQUEST_TIMEOUT_MS),
  });
  if (!upstream.ok) {
    console.error("Reply review upstream error", upstream.status, await upstream.text());
    throw new ModelUpstreamError("回复审查模型", upstream.status);
  }
  const result = (await upstream.json()) as {
    choices?: Array<{ message?: { content?: unknown } }>;
  };
  const content = result.choices?.[0]?.message?.content;
  if (typeof content !== "string" || !content.trim()) {
    throw new Error("review model returned no text");
  }
  return content;
}

async function reviewCandidate(
  config: { baseUrl: string; apiKey: string; model: string },
  messages: ChatMessage[],
  sessionMemory: string,
  liveState: string,
  candidate: string,
): Promise<ReviewResult> {
  const content = await callCompatibleModel(
    config.baseUrl,
    config.apiKey,
    config.model,
    [
      { role: "system", content: RUNTIME_TEXT.review_system_prompt },
      { role: "system", content: SKILL_BUNDLE },
      {
        role: "user",
        content: JSON.stringify({
          conversation: messages,
          session_memory: sessionMemory,
          live_state: liveState,
          candidate,
        }),
      },
    ],
    700,
  );
  const parsed = extractJsonObject(content);
  if (!parsed || typeof parsed.approved !== "boolean" || typeof parsed.problems !== "string") {
    throw new Error("review model returned invalid JSON");
  }
  return {
    approved: parsed.approved,
    problems: parsed.problems.trim().slice(0, 500),
    raw: content,
  };
}

async function selectCandidate(
  config: { baseUrl: string; apiKey: string; model: string },
  messages: ChatMessage[],
  sessionMemory: string,
  liveState: string,
  candidates: string[],
  reviews: ReviewResult[],
): Promise<{ content: string; selected: number; raw: string }> {
  const content = await callCompatibleModel(
    config.baseUrl,
    config.apiKey,
    config.model,
    [
      { role: "system", content: RUNTIME_TEXT.select_system_prompt },
      { role: "system", content: SKILL_BUNDLE },
      {
        role: "user",
        content: JSON.stringify({
          conversation: messages,
          session_memory: sessionMemory,
          live_state: liveState,
          candidates: candidates.map((candidate, index) => ({
            number: index + 1,
            content: candidate,
            review: reviews[index],
          })),
        }),
      },
    ],
    300,
  );
  const selected = extractJsonObject(content)?.selected;
  if (typeof selected !== "number" || !Number.isInteger(selected) || !candidates[selected - 1]) {
    throw new Error("review model returned invalid selection");
  }
  return { content: candidates[selected - 1], selected, raw: content };
}

export async function GET() {
  const reviewEnabled = envFlag(process.env.ENABLE_REPLY_REVIEW);
  return NextResponse.json({
    ready: Boolean(process.env.DEEPSEEK_API_KEY),
    state_ready: Boolean(
      process.env.STATE_API_KEY && process.env.STATE_BASE_URL && process.env.STATE_MODEL,
    ),
    review_enabled: reviewEnabled,
    review_ready: !reviewEnabled || Boolean(
      process.env.REVIEW_API_KEY && process.env.REVIEW_BASE_URL && process.env.REVIEW_MODEL,
    ),
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
  const reviewApiKey = process.env.REVIEW_API_KEY;
  const reviewBaseUrl = (process.env.REVIEW_BASE_URL || "").replace(/\/$/, "");
  const reviewModel = process.env.REVIEW_MODEL || "";
  const reviewEnabled = envFlag(process.env.ENABLE_REPLY_REVIEW);
  if (reviewEnabled && (!reviewApiKey || !reviewBaseUrl || !reviewModel)) {
    return NextResponse.json(
      { error: "回复审查模型的 API Key、Base URL 或模型名尚未配置。" },
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
  const requestBody = body as { messages?: unknown; memory?: unknown; liveState?: unknown };
  const messages = validateMessages(requestBody?.messages);
  const sessionMemory = validateSessionMemory(requestBody?.memory);
  const liveState = validateLiveState(requestBody?.liveState);
  if (!messages || sessionMemory === null || liveState === null) {
    return NextResponse.json({ error: "对话内容为空、过长或格式不正确。" }, { status: 400 });
  }

  const baseUrl = (process.env.DEEPSEEK_BASE_URL || "https://api.deepseek.com").replace(
    /\/$/,
    "",
  );
  const model = process.env.DEEPSEEK_MODEL || "deepseek-v4-pro";

  const generationMessages = [
    { role: "system" as const, content: RUNTIME_TEXT.persona_system_prompt },
    { role: "system" as const, content: SKILL_BUNDLE },
    { role: "system" as const, content: RUNTIME_TEXT.web_runtime_prompt },
    ...(sessionMemory
      ? [
          {
            role: "system" as const,
            content: renderRuntimeText(RUNTIME_TEXT.session_memory_prompt_template, {
              memory: sessionMemory,
            }),
          },
        ]
      : []),
    ...(liveState
      ? [
          {
            role: "system" as const,
            content: renderRuntimeText(RUNTIME_TEXT.live_state_prompt_template, {
              live_state: liveState,
            }),
          },
        ]
      : []),
    { role: "system" as const, content: RUNTIME_TEXT.response_guard_prompt },
    ...messages,
  ];

  async function generateCandidate(revision?: { candidate: string; problems: string }) {
    const upstream = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        messages: [
          ...generationMessages,
          ...(revision
            ? [
                {
                  role: "system" as const,
                  content: renderRuntimeText(RUNTIME_TEXT.revision_feedback_template, {
                    candidate: revision.candidate,
                    problems: revision.problems,
                  }),
                },
              ]
            : []),
        ],
        stream: false,
        thinking: { type: "enabled" },
        reasoning_effort: "high",
        max_tokens: 8_192,
      }),
      signal: AbortSignal.timeout(CHAT_REQUEST_TIMEOUT_MS),
    });

    if (!upstream.ok) {
      // 不把上游响应体返回给访客，避免意外泄露服务端信息。
      console.error("DeepSeek upstream error", upstream.status, await upstream.text());
      throw new ModelUpstreamError("DeepSeek API", upstream.status);
    }

    const result = (await upstream.json()) as {
      choices?: Array<{ message?: { content?: unknown } }>;
    };
    const content = result.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      throw new Error("generation model returned no text");
    }
    return content;
  }

  try {
    if (!reviewEnabled) {
      const candidate = await generateCandidate();
      const guarded = applyLocalReplyGuard(messages, candidate);
      return NextResponse.json({
        content: guarded.content,
        debug: {
          models: { chat: model, review: "" },
          candidates: [{ attempt: 1, output: candidate }],
          selected_attempt: 1,
          selector_output: "",
          review_enabled: false,
          local_guard: { applied: guarded.applied, rule: guarded.rule },
        },
      });
    }
    if (!reviewApiKey || !reviewBaseUrl || !reviewModel) {
      throw new Error("review configuration unexpectedly missing");
    }
    const reviewConfig = { baseUrl: reviewBaseUrl, apiKey: reviewApiKey, model: reviewModel };
    const candidates: string[] = [];
    const reviews: ReviewResult[] = [];
    let revision: { candidate: string; problems: string } | undefined;
    for (let attempt = 0; attempt <= MAX_REVIEW_RETRIES; attempt += 1) {
      const candidate = await generateCandidate(revision);
      const review = await reviewCandidate(
        reviewConfig,
        messages,
        sessionMemory,
        liveState,
        candidate,
      );
      candidates.push(candidate);
      reviews.push(review);
      if (review.approved) {
        return NextResponse.json({
          content: candidate,
          debug: {
            models: { chat: model, review: reviewModel },
            candidates: candidates.map((output, index) => ({
              attempt: index + 1,
              output,
              review: reviews[index],
            })),
            selected_attempt: attempt + 1,
            selector_output: "",
          },
        });
      }
      revision = {
        candidate,
        problems: review.problems || RUNTIME_TEXT.default_review_problem,
      };
    }
    const selection = await selectCandidate(
      reviewConfig,
      messages,
      sessionMemory,
      liveState,
      candidates,
      reviews,
    );
    return NextResponse.json({
      content: selection.content,
      debug: {
        models: { chat: model, review: reviewModel },
        candidates: candidates.map((output, index) => ({
          attempt: index + 1,
          output,
          review: reviews[index],
        })),
        selected_attempt: selection.selected,
        selector_output: selection.raw,
      },
    });
  } catch (error) {
    console.error("Chat request failed", error);
    const failure = publicModelFailure(error, "DeepSeek API");
    return NextResponse.json(
      { error: failure.message, error_code: failure.code },
      { status: failure.status },
    );
  }
}
