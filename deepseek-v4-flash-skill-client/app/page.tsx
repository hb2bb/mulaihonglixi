"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

const STORAGE_KEY = "flash-lab-conversation-v1";
const suggestions = [
  "用 Python 写一个带重试的异步请求函数",
  "解释这段代码可能出现的并发问题",
  "帮我设计一个简洁的 REST API",
];

function makeId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copiedId, setCopiedId] = useState("");
  const controllerRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setMessages(JSON.parse(saved) as Message[]);
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "auto";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
  }, [input]);

  async function sendMessage(content: string) {
    const cleanContent = content.trim();
    if (!cleanContent || loading) return;

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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content: text }) => ({ role, content: text })),
        }),
        signal: controller.signal,
      });
      const data = (await response.json()) as { content?: string; error?: string };
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

  function clearConversation() {
    controllerRef.current?.abort();
    setMessages([]);
    setError("");
    setLoading(false);
    localStorage.removeItem(STORAGE_KEY);
  }

  async function copyAnswer(message: Message) {
    await navigator.clipboard.writeText(message.content);
    setCopiedId(message.id);
    window.setTimeout(() => setCopiedId(""), 1_500);
  }

  const hasConversation = messages.length > 0;

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Flash Lab 首页">
          <span className="brand-mark" aria-hidden="true">F</span>
          <span>
            <strong>Flash Lab</strong>
            <small>DeepSeek V4 · Skill Enhanced</small>
          </span>
        </a>
        <div className="status-cluster">
          <span className="status"><i /> 服务在线</span>
          {hasConversation && (
            <button className="clear-button" type="button" onClick={clearConversation}>
              清空对话
            </button>
          )}
        </div>
      </header>

      <section className={`workspace ${hasConversation ? "is-chatting" : ""}`} id="top">
        {!hasConversation ? (
          <div className="welcome">
            <div className="eyebrow">CODE CONVERSATION / 04</div>
            <h1>
              把想法写下来，
              <span>让 Flash 接着跑。</span>
            </h1>
            <p className="intro">
              快速、专注的代码对话体验。每次提问都会携带当前项目 Skills，
              让模型在同一套规则和上下文里工作。
            </p>
            <div className="suggestions" aria-label="示例问题">
              {suggestions.map((suggestion, index) => (
                <button key={suggestion} type="button" onClick={() => void sendMessage(suggestion)}>
                  <span>0{index + 1}</span>
                  {suggestion}
                  <b aria-hidden="true">↗</b>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="conversation" aria-live="polite">
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-meta">
                  <span>{message.role === "user" ? "YOU" : "FLASH"}</span>
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
                <div className="message-meta"><span>FLASH</span></div>
                <div className="thinking"><i /><i /><i /><span>正在推演</span></div>
              </article>
            )}
            {error && <div className="error-banner" role="alert">{error}</div>}
            <div ref={bottomRef} />
          </div>
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
              placeholder="描述你的问题、贴一段代码，或者说说你想做什么……"
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
          <div className="composer-foot">
            <span>Enter 发送 · Shift + Enter 换行</span>
            <span>Skills 已由服务端装载</span>
          </div>
        </form>
      </section>

      <footer>
        <span>DEEPSEEK V4 FLASH</span>
        <span>回答可能有误，请核对重要信息</span>
      </footer>
    </main>
  );
}
