/** Both development frontends use the same local SQLite-backed application. */
import { NextRequest } from "next/server";

const LOCAL_ORIGIN = "http://127.0.0.1:8765";

async function forward(request: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const hostname = request.nextUrl.hostname;
  if (hostname !== "localhost" && hostname !== "127.0.0.1") {
    return Response.json({ error: "本地 Demo 只允许本机访问。" }, { status: 403 });
  }
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return Response.json({ error: "不允许跨站请求。" }, { status: 403 });
  }
  const { path = [] } = await context.params;
  if (path.some(part => !/^[a-zA-Z0-9_.-]+$/.test(part) || part === "..")) {
    return Response.json({ error: "路径无效。" }, { status: 400 });
  }
  const target = `${LOCAL_ORIGIN}/${path.join("/")}${request.nextUrl.search}`;
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        "X-Local-Token": request.headers.get("x-local-token") || "",
        Origin: LOCAL_ORIGIN,
      },
      body: request.method === "POST" ? await request.text() : undefined,
      signal: AbortSignal.timeout(150_000),
    });
    let content = await upstream.text();
    if (!path.length) {
      content = content.replace('href="/style.css"', 'href="/demo/style.css"')
        .replace('src="/app.js"', 'src="/demo/app.js"').replace('href="/"', 'href="/demo"');
    }
    const headers = new Headers(upstream.headers);
    headers.delete("content-length");
    headers.delete("content-encoding");
    return new Response(content, { status: upstream.status, headers });
  } catch {
    return Response.json({ error: "请先运行 npm run demo，启动本地数据服务。" }, { status: 503 });
  }
}
export const GET = forward;
export const POST = forward;
