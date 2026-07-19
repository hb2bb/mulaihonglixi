import { NextRequest, NextResponse } from "next/server";
import { RUNTIME_TEXT } from "@/lib/skill-bundle.generated";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type MoodResult = {
  mood: string;
  intensity: number;
  reason: string;
  behavior: string;
};

const MAX_MESSAGES = 10;
const MAX_CONTEXT_LENGTH = 4_000;
const MAX_STATE_LENGTH = 3_000;
const RATE_LIMIT = 4;
const RATE_LIMIT_WINDOW_MS = 60_000;

const globalRateLimit = globalThis as typeof globalThis & {
  flashLabStateRequests?: Map<string, number[]>;
};
const requestRecords = (globalRateLimit.flashLabStateRequests ??= new Map());

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

function validateText(value: unknown, maxLength: number): string | null {
  if (value === undefined || value === "") return "";
  if (typeof value !== "string" || value.length > maxLength) return null;
  return value.trim();
}

function validateMessages(value: unknown): ChatMessage[] | null {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > MAX_MESSAGES) return null;
  const messages: ChatMessage[] = [];
  let totalLength = 0;
  for (const item of value) {
    if (!item || typeof item !== "object") return null;
    const { role, content } = item as Record<string, unknown>;
    if (role !== "user" && role !== "assistant") return null;
    if (typeof content !== "string" || !content.trim() || content.length > 12_000) return null;
    totalLength += content.length;
    if (totalLength > 30_000) return null;
    messages.push({ role, content });
  }
  return messages;
}

function weatherLabel(code: number | undefined) {
  if (code === 0) return "晴";
  if (code !== undefined && code <= 3) return "多云";
  if (code === 45 || code === 48) return "有雾";
  if (code !== undefined && code >= 51 && code <= 57) return "毛毛雨";
  if (code !== undefined && code >= 61 && code <= 67) return "下雨";
  if (code !== undefined && code >= 71 && code <= 77) return "下雪";
  if (code !== undefined && code >= 80 && code <= 82) return "阵雨";
  if (code !== undefined && code >= 85 && code <= 86) return "阵雪";
  if (code !== undefined && code >= 95) return "雷雨";
  return "天气状况未知";
}

async function loadWeather() {
  const city = process.env.LIVE_STATE_CITY || "北京";
  const latitude = process.env.LIVE_STATE_LATITUDE || "39.9042";
  const longitude = process.env.LIVE_STATE_LONGITUDE || "116.4074";
  const timezone = process.env.LIVE_STATE_TIMEZONE || "Asia/Shanghai";
  const url = new URL("https://api.open-meteo.com/v1/forecast");
  url.searchParams.set("latitude", latitude);
  url.searchParams.set("longitude", longitude);
  url.searchParams.set(
    "current",
    "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
  );
  url.searchParams.set("timezone", timezone);

  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(8_000) });
    if (!response.ok) throw new Error(`weather HTTP ${response.status}`);
    const data = (await response.json()) as {
      current?: {
        temperature_2m?: number;
        apparent_temperature?: number;
        weather_code?: number;
        wind_speed_10m?: number;
      };
    };
    const current = data.current;
    if (!current || typeof current.temperature_2m !== "number") {
      throw new Error("weather response missing current data");
    }
    return {
      city,
      summary: `${weatherLabel(current.weather_code)}，${current.temperature_2m}°C，体感 ${current.apparent_temperature ?? current.temperature_2m}°C，风速 ${current.wind_speed_10m ?? 0} km/h`,
    };
  } catch (error) {
    console.error("Live weather request failed", error);
    return { city, summary: "天气暂时不可用" };
  }
}

function parseMood(content: string): MoodResult | null {
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    const value = JSON.parse(content.slice(start, end + 1)) as Partial<MoodResult>;
    if (
      typeof value.mood !== "string" ||
      typeof value.intensity !== "number" ||
      typeof value.reason !== "string" ||
      typeof value.behavior !== "string"
    ) {
      return null;
    }
    return {
      mood: value.mood.slice(0, 20),
      intensity: Math.max(1, Math.min(5, Math.round(value.intensity))),
      reason: value.reason.slice(0, 60),
      behavior: value.behavior.slice(0, 100),
    };
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest) {
  const apiKey = process.env.STATE_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "服务尚未配置状态模型 API Key。" }, { status: 503 });
  }
  const accessKey = process.env.SITE_ACCESS_KEY;
  if (accessKey && !safeEqual(request.headers.get("X-Flash-Lab-Access") || "", accessKey)) {
    return NextResponse.json({ error: "体验访问码不正确。" }, { status: 401 });
  }
  if (!allowRequest(clientIdentity(request))) {
    return NextResponse.json(
      { error: "状态刷新请求过于频繁，请稍后再试。" },
      { status: 429, headers: { "Retry-After": "60" } },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "请求不是有效的 JSON。" }, { status: 400 });
  }
  const requestBody = body as {
    memory?: unknown;
    currentState?: unknown;
    messages?: unknown;
  };
  const memory = validateText(requestBody?.memory, MAX_CONTEXT_LENGTH);
  const currentState = validateText(requestBody?.currentState, MAX_STATE_LENGTH);
  const messages = validateMessages(requestBody?.messages);
  if (memory === null || currentState === null || messages === null) {
    return NextResponse.json({ error: "状态上下文过长或格式不正确。" }, { status: 400 });
  }

  const timezone = process.env.LIVE_STATE_TIMEZONE || "Asia/Shanghai";
  const now = new Date();
  const localTime = new Intl.DateTimeFormat("zh-CN", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(now);
  const weather = await loadWeather();
  const baseUrl = (process.env.STATE_BASE_URL || "").replace(/\/$/, "");
  const model = process.env.STATE_MODEL || "";
  if (!baseUrl || !model) {
    return NextResponse.json({ error: "状态模型的 Base URL 或模型名尚未配置。" }, { status: 503 });
  }
  let mood: MoodResult = {
    mood: "平静",
    intensity: 2,
    reason: "没有足够信息改变状态",
    behavior: "正常简短地聊天，偶尔轻损一句",
  };
  let modelOutput = "状态模型未返回有效输出，使用默认心情。";

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
          { role: "system", content: RUNTIME_TEXT.mood_system_prompt },
          {
            role: "user",
            content: JSON.stringify({
              local_time: localTime,
              location: weather.city,
              weather: weather.summary,
              previous_state: currentState,
              session_memory: memory,
              recent_conversation: messages,
            }),
          },
        ],
        stream: false,
        max_tokens: 600,
      }),
    });
    if (upstream.ok) {
      const result = (await upstream.json()) as {
        choices?: Array<{ message?: { content?: unknown } }>;
      };
      const content = result.choices?.[0]?.message?.content;
      if (typeof content === "string") modelOutput = content;
      const parsed = typeof content === "string" ? parseMood(content) : null;
      if (parsed) mood = parsed;
    } else {
      console.error("DeepSeek state upstream error", upstream.status, await upstream.text());
    }
  } catch (error) {
    console.error("DeepSeek state request failed", error);
  }

  const state = [
    `- 更新时间：${localTime}`,
    "- 有效期：30 分钟",
    `- 地点：${weather.city}`,
    `- 天气：${weather.summary}`,
    `- 角色心情：${mood.mood}`,
    `- 心情强度：${mood.intensity}/5`,
    `- 状态缘由：${mood.reason}`,
    `- 对话倾向：${mood.behavior}`,
  ].join("\n");

  return NextResponse.json({
    state,
    debug: { model, output: modelOutput },
    updated_at: now.toISOString(),
    expires_at: new Date(now.getTime() + 30 * 60_000).toISOString(),
  });
}
