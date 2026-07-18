"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const STORAGE_KEY = "flash-lab-conversation-v1";
const ACCESS_KEY_STORAGE = "flash-lab-access-key";
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
  const [accessKey, setAccessKey] = useState("");
  const [accessKeyInput, setAccessKeyInput] = useState("");
  const [pendingContent, setPendingContent] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const accessDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    // 清理旧版本的持久化记录；刷新或重新进入网站时始终从空对话开始。
    localStorage.removeItem(STORAGE_KEY);
    setMessages([]);
    setAccessKey(sessionStorage.getItem(ACCESS_KEY_STORAGE) || "");

    void fetch("/api/chat")
      .then((response) => response.json())
      .then((status: { access_key_required?: boolean }) => {
        setAccessKeyRequired(Boolean(status.access_key_required));
      })
      .catch(() => setAccessKeyRequired(false));
  }, []);

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
        }),
        signal: controller.signal,
      });
      const data = (await response.json()) as { content?: string; error?: string };
      if (response.status === 401) {
        sessionStorage.removeItem(ACCESS_KEY_STORAGE);
        setAccessKey("");
        setMessages(messages);
        setInput(cleanContent);
        requestAccessKey(cleanContent);
      }
      if (!response.ok || !data.content) throw new Error(data.error || "请求失败");
      setMessages((current) => [
        ...current,
        { id: makeId(), role: "assistant", content: data.content as string },
      ]);
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
    controllerRef.current = null;
    setMessages([]);
    setInput("");
    setError("");
    setLoading(false);
    textareaRef.current?.focus();
  }

  const hasConversation = messages.length > 0;

  return (
    <main className="app-shell">
      <section className={`workspace ${hasConversation ? "is-chatting" : ""}`} id="top">
        {hasConversation && (
          <>
            <div className="chat-toolbar">
              <button className="clear-chat-button" type="button" onClick={clearConversation}>
                清空对话
              </button>
            </div>
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
