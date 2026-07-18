"use strict";

// 仅用于清理旧版本曾保存在浏览器里的历史记录。
const STORAGE_KEY = "flash-lab-conversation-v1";
const state = {
  messages: [], loading: false, controller: null, error: "", accessKeyRequired: false,
};

const elements = {
  workspace: document.querySelector(".workspace"),
  conversation: document.querySelector("#conversation"),
  composer: document.querySelector("#composer"),
  prompt: document.querySelector("#prompt"),
  sendButton: document.querySelector("#send-button"),
  chatToolbar: document.querySelector("#chat-toolbar"),
  clearChatButton: document.querySelector("#clear-chat-button"),
  accessDialog: document.querySelector("#access-dialog"),
  accessForm: document.querySelector("#access-form"),
  accessKey: document.querySelector("#access-key"),
  accessCancel: document.querySelector("#access-cancel"),
};

function makeId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createMessageElement(message) {
  const article = document.createElement("article");
  article.className = `message ${message.role}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const role = document.createElement("span");
  role.textContent = message.role === "user" ? "YOU" : "FLASH";
  meta.append(role);

  if (message.role === "assistant") {
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "复制";
    copy.addEventListener("click", async () => {
      await navigator.clipboard.writeText(message.content);
      copy.textContent = "已复制";
      window.setTimeout(() => { copy.textContent = "复制"; }, 1500);
    });
    meta.append(copy);
  }

  const body = document.createElement("div");
  body.className = "message-body";
  // 使用 textContent 渲染模型输出，避免把模型生成的 HTML 当作页面代码执行。
  body.textContent = message.content;
  article.append(meta, body);
  return article;
}

function createThinkingElement() {
  const article = document.createElement("article");
  article.className = "message assistant thinking-message";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.innerHTML = "<span>FLASH</span>";
  const body = document.createElement("div");
  body.className = "thinking";
  body.innerHTML = "<i></i><i></i><i></i><span>正在推演</span>";
  article.append(meta, body);
  return article;
}

function render() {
  const hasConversation = state.messages.length > 0 || state.loading || Boolean(state.error);
  elements.conversation.hidden = !hasConversation;
  elements.chatToolbar.hidden = !hasConversation;
  elements.workspace.classList.toggle("is-chatting", hasConversation);
  elements.conversation.replaceChildren(...state.messages.map(createMessageElement));
  if (state.loading) elements.conversation.append(createThinkingElement());
  if (state.error) setError(state.error);
  elements.conversation.lastElementChild?.scrollIntoView({ behavior: "smooth" });
  elements.sendButton.disabled = !state.loading && !elements.prompt.value.trim();
  elements.sendButton.classList.toggle("stop-button", state.loading);
  elements.sendButton.setAttribute("aria-label", state.loading ? "停止生成" : "发送");
  elements.sendButton.textContent = state.loading ? "■" : "↑";
}

function setError(message) {
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.setAttribute("role", "alert");
  banner.textContent = message;
  elements.conversation.append(banner);
}

async function sendMessage(rawContent) {
  const content = rawContent.trim();
  if (!content || state.loading) return;
  if (!(await ensureAccessKey())) return;

  state.messages.push({ id: makeId(), role: "user", content });
  elements.prompt.value = "";
  state.error = "";
  state.loading = true;
  state.controller = new AbortController();
  resizePrompt();
  render();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Flash-Lab-Access": sessionStorage.getItem("flash-lab-access-key") || "",
      },
      body: JSON.stringify({
        messages: state.messages.map(({ role, content: text }) => ({ role, content: text })),
      }),
      signal: state.controller.signal,
    });
    const data = await response.json();
    if (response.status === 401) sessionStorage.removeItem("flash-lab-access-key");
    if (!response.ok || typeof data.content !== "string") {
      throw new Error(data.error || "请求失败，请稍后重试。");
    }
    state.messages.push({ id: makeId(), role: "assistant", content: data.content });
    render();
  } catch (error) {
    if (error.name !== "AbortError") {
      state.error = error.message || "请求失败，请稍后重试。";
    }
  } finally {
    state.loading = false;
    state.controller = null;
    render();
    elements.prompt.focus();
  }
}

function ensureAccessKey() {
  if (!state.accessKeyRequired || sessionStorage.getItem("flash-lab-access-key")) {
    return Promise.resolve(true);
  }
  elements.accessKey.value = "";
  elements.accessDialog.showModal();
  window.setTimeout(() => elements.accessKey.focus(), 0);
  return new Promise((resolve) => {
    const submit = (event) => {
      event.preventDefault();
      sessionStorage.setItem("flash-lab-access-key", elements.accessKey.value);
      elements.accessDialog.close();
      cleanup();
      resolve(true);
    };
    const cancel = () => {
      elements.accessDialog.close();
      cleanup();
      resolve(false);
    };
    const cancelDialog = (event) => {
      event.preventDefault();
      cancel();
    };
    const cleanup = () => {
      elements.accessForm.removeEventListener("submit", submit);
      elements.accessCancel.removeEventListener("click", cancel);
      elements.accessDialog.removeEventListener("cancel", cancelDialog);
    };
    elements.accessForm.addEventListener("submit", submit);
    elements.accessCancel.addEventListener("click", cancel);
    elements.accessDialog.addEventListener("cancel", cancelDialog);
  });
}

function resizePrompt() {
  elements.prompt.style.height = "auto";
  elements.prompt.style.height = `${Math.min(elements.prompt.scrollHeight, 180)}px`;
}

elements.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.loading) {
    state.controller?.abort();
    return;
  }
  void sendMessage(elements.prompt.value);
});

elements.prompt.addEventListener("input", () => {
  resizePrompt();
  elements.sendButton.disabled = !state.loading && !elements.prompt.value.trim();
});

elements.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void sendMessage(elements.prompt.value);
  }
});

elements.clearChatButton.addEventListener("click", () => {
  // 若模型仍在生成，先终止请求，避免旧回答在清空后重新写回页面。
  state.controller?.abort();
  state.messages = [];
  state.loading = false;
  state.controller = null;
  state.error = "";
  elements.prompt.value = "";
  resizePrompt();
  render();
  elements.prompt.focus();
});

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    state.accessKeyRequired = Boolean(status.access_key_required);
  } catch {
    state.accessKeyRequired = false;
  }
}

// 每次加载网站都清空旧历史；本次对话只存在于当前页面的内存中。
localStorage.removeItem(STORAGE_KEY);
render();
void loadStatus();
