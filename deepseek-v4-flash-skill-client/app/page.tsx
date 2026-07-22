"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type DebugEntry = {
  id: string;
  label: string;
  model: string;
  output: string;
};

type ChatDebug = {
  models?: { chat?: unknown; review?: unknown };
  candidates?: Array<{
    attempt?: number;
    output?: unknown;
    review?: { approved?: unknown; problems?: unknown; raw?: unknown };
  }>;
  selected_attempt?: unknown;
  selector_output?: unknown;
};

const STORAGE_KEY = "flash-lab-conversation-v1";
const ACCESS_KEY_STORAGE = "flash-lab-access-key";
const MEMORY_CHECK_INTERVAL = 10;
const STATE_REFRESH_INTERVAL_MS = 30 * 60_000;
function makeId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copiedId, setCopiedId] = useState("");
  const [accessKeyRequired, setAccessKeyRequired] = useState(false);
  const [statusReady, setStatusReady] = useState(false);
  const [accessKey, setAccessKey] = useState(() => (
    typeof window === "undefined" ? "" : sessionStorage.getItem(ACCESS_KEY_STORAGE) || ""
  ));
  const [accessKeyInput, setAccessKeyInput] = useState("");
  const [pendingContent, setPendingContent] = useState("");
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugMemory, setDebugMemory] = useState("");
  const [debugLiveState, setDebugLiveState] = useState("");
  const [debugEntries, setDebugEntries] = useState<DebugEntry[]>([]);
  const controllerRef = useRef<AbortController | null>(null);
  const memoryControllerRef = useRef<AbortController | null>(null);
  const stateControllerRef = useRef<AbortController | null>(null);
  const lastMemoryCheckCountRef = useRef(0);
  const messagesRef = useRef<Message[]>([]);
  const sessionMemoryRef = useRef("");
  const liveStateRef = useRef("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const accessDialogRef = useRef<HTMLDialogElement>(null);

  const appendDebug = useCallback((entries: Omit<DebugEntry, "id">[]) => {
    if (!entries.length) return;
    setDebugEntries((current) => [
      ...current,
      ...entries.map((entry) => ({ ...entry, id: makeId() })),
    ].slice(-100));
  }, []);

  const refreshLiveState = useCallback(
    async (requestAccess: string, memoryOverride?: string) => {
      stateControllerRef.current?.abort();
      const controller = new AbortController();
      stateControllerRef.current = controller;
      try {
        const response = await fetch("/api/state", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Flash-Lab-Access": requestAccess,
          },
          body: JSON.stringify({
            memory: memoryOverride ?? sessionMemoryRef.current,
            currentState: liveStateRef.current,
            messages: messagesRef.current
              .slice(-MEMORY_CHECK_INTERVAL)
              .map(({ role, content }) => ({ role, content })),
          }),
          signal: controller.signal,
        });
        const data = (await response.json()) as {
          state?: unknown;
          error?: unknown;
          debug?: { model?: unknown; output?: unknown; degraded?: unknown };
        };
        if (response.ok && typeof data.state === "string") {
          liveStateRef.current = data.state;
          setDebugLiveState(data.state);
          if (typeof data.debug?.output === "string") {
            appendDebug([{
              label: "状态模型输出",
              model: typeof data.debug.model === "string" ? data.debug.model : "STATE_MODEL",
              output: data.debug.output,
            }]);
          }
        } else if (typeof data.error === "string") {
          appendDebug([{
            label: "状态模型错误",
            model: "STATE_MODEL",
            output: data.error,
          }]);
        }
      } catch (stateError) {
        if ((stateError as Error).name !== "AbortError") {
          console.error("Live state update failed", stateError);
        }
      } finally {
        if (stateControllerRef.current === controller) stateControllerRef.current = null;
      }
    },
    [appendDebug],
  );

  useEffect(() => {
    // 清理旧版本的持久化记录；刷新或重新进入网站时始终从空对话开始。
    localStorage.removeItem(STORAGE_KEY);

    void fetch("/api/chat")
      .then((response) => response.json())
      .then((status: { access_key_required?: boolean }) => {
        setAccessKeyRequired(Boolean(status.access_key_required));
      })
      .catch(() => setAccessKeyRequired(false))
      .finally(() => setStatusReady(true));

    return () => {
      controllerRef.current?.abort();
      memoryControllerRef.current?.abort();
      stateControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!statusReady || (accessKeyRequired && !accessKey)) return;
    void refreshLiveState(accessKey);
    const interval = window.setInterval(
      () => void refreshLiveState(accessKey),
      STATE_REFRESH_INTERVAL_MS,
    );
    return () => window.clearInterval(interval);
  }, [accessKey, accessKeyRequired, refreshLiveState, statusReady]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
  }, [input]);

  function requestAccessKey(content: string) {
    setPendingContent(content);
    setAccessKeyInput("");
    accessDialogRef.current?.showModal();
  }

  async function refreshSessionMemory(completedMessages: Message[], requestAccess: string) {
    memoryControllerRef.current?.abort();
    const controller = new AbortController();
    memoryControllerRef.current = controller;
    let shouldRefreshMood = true;
    try {
      const response = await fetch("/api/memory", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Flash-Lab-Access": requestAccess,
        },
        body: JSON.stringify({
          memory: sessionMemoryRef.current,
          messages: completedMessages
            .slice(-MEMORY_CHECK_INTERVAL)
            .map(({ role, content }) => ({ role, content })),
        }),
        signal: controller.signal,
      });
      const data = (await response.json()) as {
        memory?: unknown;
        error?: unknown;
        debug?: { model?: unknown; output?: unknown };
      };
      if (response.ok && typeof data.memory === "string") {
        sessionMemoryRef.current = data.memory;
        setDebugMemory(data.memory);
        if (typeof data.debug?.output === "string") {
          appendDebug([{
            label: "记忆模型输出",
            model: typeof data.debug.model === "string" ? data.debug.model : "DEEPSEEK_MEMORY_MODEL",
            output: data.debug.output,
          }]);
        }
      } else if (typeof data.error === "string") {
        appendDebug([{
          label: "记忆模型错误",
          model: "DEEPSEEK_MEMORY_MODEL",
          output: data.error,
        }]);
      }
    } catch (memoryError) {
      if ((memoryError as Error).name === "AbortError") {
        shouldRefreshMood = false;
      } else {
        console.error("Session memory update failed", memoryError);
      }
    } finally {
      if (memoryControllerRef.current === controller) memoryControllerRef.current = null;
      if (shouldRefreshMood) {
        void refreshLiveState(requestAccess, sessionMemoryRef.current);
      }
    }
  }

  async function sendMessage(content: string, keyOverride?: string) {
    const cleanContent = content.trim();
    if (!cleanContent || loading) return;
    const requestAccess = keyOverride || accessKey;
    if (accessKeyRequired && !requestAccess) {
      requestAccessKey(cleanContent);
      return;
    }

    const userMessage: Message = { id: makeId(), role: "user", content: cleanContent };
    const nextMessages = [...messages, userMessage];
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
    setInput("");
    setError("");
    setLoading(true);

    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Flash-Lab-Access": requestAccess,
        },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content: text }) => ({ role, content: text })),
          memory: sessionMemoryRef.current,
          liveState: liveStateRef.current,
        }),
        signal: controller.signal,
      });
      const data = (await response.json()) as {
        content?: string;
        error?: string;
        debug?: ChatDebug;
      };
      if (response.status === 401) {
        sessionStorage.removeItem(ACCESS_KEY_STORAGE);
        setAccessKey("");
        setMessages(messages);
        setInput(cleanContent);
        requestAccessKey(cleanContent);
      }
      if (!response.ok || !data.content) throw new Error(data.error || "请求失败");
      const chatDebugEntries: Omit<DebugEntry, "id">[] = [];
      const chatModel = typeof data.debug?.models?.chat === "string"
        ? data.debug.models.chat
        : "DEEPSEEK_MODEL";
      const reviewModel = typeof data.debug?.models?.review === "string"
        ? data.debug.models.review
        : "REVIEW_MODEL";
      for (const item of data.debug?.candidates || []) {
        const attempt = typeof item.attempt === "number" ? item.attempt : chatDebugEntries.length + 1;
        if (typeof item.output === "string") {
          chatDebugEntries.push({
            label: `聊天模型候选 ${attempt}`,
            model: chatModel,
            output: item.output,
          });
        }
        if (typeof item.review?.raw === "string") {
          chatDebugEntries.push({
            label: `审查模型结果 ${attempt}`,
            model: reviewModel,
            output: item.review.raw,
          });
        }
      }
      if (typeof data.debug?.selector_output === "string" && data.debug.selector_output) {
        chatDebugEntries.push({
          label: "审查模型最终选择",
          model: reviewModel,
          output: data.debug.selector_output,
        });
      }
      appendDebug(chatDebugEntries);
      const assistantMessage: Message = {
        id: makeId(),
        role: "assistant",
        content: data.content,
      };
      const completedMessages = [...nextMessages, assistantMessage];
      messagesRef.current = completedMessages;
      setMessages(completedMessages);
      if (
        completedMessages.length % MEMORY_CHECK_INTERVAL === 0 &&
        lastMemoryCheckCountRef.current !== completedMessages.length
      ) {
        lastMemoryCheckCountRef.current = completedMessages.length;
        void refreshSessionMemory(completedMessages, requestAccess);
      }
    } catch (requestError) {
      if ((requestError as Error).name !== "AbortError") {
        setError((requestError as Error).message || "请求失败，请稍后重试。");
      }
    } finally {
      controllerRef.current = null;
      setLoading(false);
      textareaRef.current?.focus();
    }
  }

  function submitAccessKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextAccessKey = accessKeyInput.trim();
    if (!nextAccessKey) return;
    sessionStorage.setItem(ACCESS_KEY_STORAGE, nextAccessKey);
    setAccessKey(nextAccessKey);
    accessDialogRef.current?.close();
    const content = pendingContent;
    setPendingContent("");
    if (content) void sendMessage(content, nextAccessKey);
    else void refreshLiveState(nextAccessKey);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(input);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void sendMessage(input);
    }
  }

  async function copyAnswer(message: Message) {
    await navigator.clipboard.writeText(message.content);
    setCopiedId(message.id);
    window.setTimeout(() => setCopiedId(""), 1_500);
  }

  function clearConversation() {
    // 清空时同时终止未完成的请求，防止旧回答随后重新出现在页面中。
    controllerRef.current?.abort();
    memoryControllerRef.current?.abort();
    stateControllerRef.current?.abort();
    controllerRef.current = null;
    memoryControllerRef.current = null;
    stateControllerRef.current = null;
    setMessages([]);
    messagesRef.current = [];
    sessionMemoryRef.current = "";
    liveStateRef.current = "";
    setDebugMemory("");
    setDebugLiveState("");
    setDebugEntries([]);
    lastMemoryCheckCountRef.current = 0;
    setInput("");
    setError("");
    setLoading(false);
    if (!accessKeyRequired || accessKey) void refreshLiveState(accessKey, "");
    textareaRef.current?.focus();
  }

  const hasConversation = messages.length > 0 || Boolean(debugLiveState);

  return (
    <main className="app-shell">
      <section className={`workspace ${hasConversation ? "is-chatting" : ""}`} id="top">
        {hasConversation && (
          <>
            <div className="chat-toolbar">
              <button
                className="clear-chat-button"
                type="button"
                onClick={() => setDebugOpen((value) => !value)}
              >
                {debugOpen ? "收起 Debug" : "展开 Debug"}
              </button>
              <button className="clear-chat-button" type="button" onClick={clearConversation}>
                清空对话
              </button>
            </div>
            {debugOpen && (
              <aside className="debug-panel">
                <div className="debug-grid">
                  <section>
                    <h2>当前会话记忆</h2>
                    <pre>{debugMemory || "尚未生成记忆"}</pre>
                  </section>
                  <section>
                    <h2>当前实时状态</h2>
                    <pre>{debugLiveState || "尚未生成状态"}</pre>
                  </section>
                </div>
                <section className="debug-trace">
                  <h2>模型输出轨迹</h2>
                  {debugEntries.length === 0 ? (
                    <p>尚无模型输出</p>
                  ) : (
                    debugEntries.map((entry) => (
                      <details key={entry.id} open={debugEntries.length <= 4}>
                        <summary>{entry.label} · {entry.model}</summary>
                        <pre>{entry.output}</pre>
                      </details>
                    ))
                  )}
                </section>
              </aside>
            )}
            <div className="conversation" aria-live="polite">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-meta">
                  <span>{message.role === "user" ? "YOU" : "PRO"}</span>
                  {message.role === "assistant" && (
                    <button type="button" onClick={() => void copyAnswer(message)}>
                      {copiedId === message.id ? "已复制" : "复制"}
                    </button>
                  )}
                </div>
                <div className="message-body">{message.content}</div>
              </article>
            ))}
            {loading && (
              <article className="message assistant thinking-message">
                <div className="message-meta"><span>PRO</span></div>
                <div className="thinking"><i /><i /><i /><span>正在推演</span></div>
              </article>
            )}
            {error && <div className="error-banner" role="alert">{error}</div>}
            <div ref={bottomRef} />
            </div>
          </>
        )}

        <form className="composer" onSubmit={submit}>
          <div className="composer-inner">
            <label className="sr-only" htmlFor="prompt">输入问题</label>
            <textarea
              id="prompt"
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="给 DeepSeek V4 Pro 发消息……"
              rows={1}
              maxLength={12_000}
              disabled={loading}
            />
            {loading ? (
              <button
                className="send-button stop-button"
                type="button"
                onClick={() => controllerRef.current?.abort()}
                aria-label="停止生成"
              >
                <span />
              </button>
            ) : (
              <button className="send-button" type="submit" disabled={!input.trim()} aria-label="发送">
                ↑
              </button>
            )}
          </div>
        </form>
      </section>

      <dialog className="access-dialog" ref={accessDialogRef}>
        <form onSubmit={submitAccessKey}>
          <h2>输入体验访问码</h2>
          <p>这个站点限制了模型调用，请向站点所有者获取访问码。</p>
          <label className="sr-only" htmlFor="access-key">体验访问码</label>
          <input
            id="access-key"
            type="password"
            autoComplete="current-password"
            value={accessKeyInput}
            onChange={(event) => setAccessKeyInput(event.target.value)}
            required
          />
          <div>
            <button type="button" onClick={() => accessDialogRef.current?.close()}>取消</button>
            <button type="submit">继续</button>
          </div>
        </form>
      </dialog>
    </main>
  );
}
