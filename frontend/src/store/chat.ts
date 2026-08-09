/**
 * 对话 Pinia store：管理消息列表、会话 ID、发送状态、历史分页加载。
 * 组件只调用 action，不直接修改 state。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchHistory, sendChat } from '@/api/chatApi'
import { useSSE } from '@/hooks/useSSE'
import type { ChatMessage } from '@/types/chat'
import { nowIso } from '@/utils/datetime'

/** 历史分页每页条数 */
const HISTORY_PAGE_SIZE = 20
/** localStorage 中保存最近会话 ID 的 key */
const SESSION_STORAGE_KEY = 'ai-girlfriend-session-id'

export const useChatStore = defineStore('chat', () => {
  // ---- state ----
  /** 消息列表（单会话，时间正序：最旧在前，最新在后） */
  const messages = ref<ChatMessage[]>([])
  /** 当前会话 ID，首次为 null */
  const sessionId = ref<string | null>(null)
  /** 是否正在发送/接收中 */
  const isSending = ref(false)
  /** 是否正在加载历史（初始加载或向上翻页） */
  const isLoadingHistory = ref(false)
  /** 是否还有更早的历史可加载 */
  const hasMoreHistory = ref(false)
  /** 已从最新端加载的历史条数（用于下次翻页的 offset） */
  const historyOffset = ref(0)
  /** 错误信息（空表示无错误） */
  const errorMessage = ref('')
  /** 是否使用流式模式 */
  const useStream = ref(true)

  // ---- SSE hook（需在 setup 作用域内调用，这里在 store 中合法） ----
  const { isStreaming, sendStream, closeStream } = useSSE({
    onChunk: (chunk: string) => {
      // 把 chunk 追加到最后一条 assistant 消息
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') {
        last.content += chunk
      }
    },
    onDone: (data) => {
      sessionId.value = data.session_id
      persistSessionId(data.session_id)
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') {
        last.streaming = false
        last.datetime = data.datetime
      }
      isSending.value = false
    },
    onError: (msg: string) => {
      errorMessage.value = msg
      const last = messages.value[messages.value.length - 1]
      if (last && last.role === 'assistant') {
        last.streaming = false
        if (!last.content) {
          last.content = '（连接异常，请重试）'
        }
      }
      isSending.value = false
    },
  })

  // ---- helpers ----

  /** 读取 localStorage 中最近会话 ID */
  function readPersistedSessionId(): string | null {
    try {
      return localStorage.getItem(SESSION_STORAGE_KEY)
    } catch {
      return null
    }
  }

  /** 写入 localStorage 最近会话 ID */
  function persistSessionId(sid: string): void {
    try {
      if (sid) localStorage.setItem(SESSION_STORAGE_KEY, sid)
    } catch {
      /* localStorage 不可用时静默忽略 */
    }
  }

  // ---- actions ----

  /**
   * 进入页面时加载最近会话的初始历史（最新的一页，时间正序）。
   * 若 localStorage 有上次会话则恢复该会话，否则交给后端定位最近会话。
   */
  async function loadInitialHistory(): Promise<void> {
    if (isLoadingHistory.value || messages.value.length > 0) return
    isLoadingHistory.value = true
    errorMessage.value = ''
    try {
      const stored = readPersistedSessionId()
      const data = await fetchHistory({
        session_id: stored ?? null,
        offset: 0,
        limit: HISTORY_PAGE_SIZE,
      })
      sessionId.value = data.session_id || null
      if (data.session_id) persistSessionId(data.session_id)
      messages.value = data.messages.map((m) => ({
        role: m.role,
        content: m.content,
        datetime: m.datetime,
      }))
      historyOffset.value = data.messages.length
      hasMoreHistory.value = data.has_more
    } catch (err) {
      const msg = err instanceof Error ? err.message : '历史加载失败'
      errorMessage.value = msg
      messages.value = []
      hasMoreHistory.value = false
      historyOffset.value = 0
    } finally {
      isLoadingHistory.value = false
    }
  }

  /**
   * 向上滚动时加载更早的历史，并**前插**到消息列表头部（保持时间正序）。
   */
  async function loadOlderHistory(): Promise<void> {
    if (isLoadingHistory.value || !hasMoreHistory.value || isSending.value) return
    isLoadingHistory.value = true
    errorMessage.value = ''
    try {
      const data = await fetchHistory({
        session_id: sessionId.value,
        offset: historyOffset.value,
        limit: HISTORY_PAGE_SIZE,
      })
      const older = data.messages.map((m) => ({
        role: m.role as ChatMessage['role'],
        content: m.content,
        datetime: m.datetime,
      }))
      messages.value = [...older, ...messages.value]
      historyOffset.value = historyOffset.value + data.messages.length
      hasMoreHistory.value = data.has_more
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更早历史加载失败'
      errorMessage.value = msg
    } finally {
      isLoadingHistory.value = false
    }
  }

  /**
   * 发送消息（根据 useStream 选择流式或非流式）。
   * @param text 用户输入文本
   */
  async function sendMessage(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || isSending.value) return

    errorMessage.value = ''
    isSending.value = true

    // 立即追加用户消息
    const userMsg: ChatMessage = {
      role: 'user',
      content: trimmed,
      datetime: nowIso(),
    }
    messages.value.push(userMsg)

    // 预占一条 assistant 消息（流式时逐步填充）
    const assistantMsg: ChatMessage = {
      role: 'assistant',
      content: '',
      datetime: '',
      streaming: true,
    }
    messages.value.push(assistantMsg)

    // 新消息到达尾部即是最新，翻页 offset 相应增加
    historyOffset.value += 2

    try {
      if (useStream.value) {
        sendStream({ message: trimmed, session_id: sessionId.value })
      } else {
        const data = await sendChat({ message: trimmed, session_id: sessionId.value })
        sessionId.value = data.session_id
        persistSessionId(data.session_id)
        assistantMsg.content = data.reply
        assistantMsg.datetime = data.datetime
        assistantMsg.streaming = false
        isSending.value = false
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发送失败'
      errorMessage.value = msg
      assistantMsg.content = '（发送失败，请重试）'
      assistantMsg.streaming = false
      isSending.value = false
    }
  }

  /**
   * 清空当前会话消息（不删除后端历史）。
   */
  function clearMessages(): void {
    messages.value = []
    errorMessage.value = ''
  }

  /**
   * 重置会话：清空消息 + 生成新 session_id。
   */
  function resetSession(): void {
    closeStream()
    clearMessages()
    sessionId.value = null
    historyOffset.value = 0
    hasMoreHistory.value = false
    try {
      localStorage.removeItem(SESSION_STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }

  /**
   * 切换流式/非流式模式。
   */
  function toggleStream(): void {
    useStream.value = !useStream.value
  }

  return {
    // state
    messages,
    sessionId,
    isSending,
    isLoadingHistory,
    hasMoreHistory,
    historyOffset,
    errorMessage,
    useStream,
    isStreaming,
    // actions
    sendMessage,
    loadInitialHistory,
    loadOlderHistory,
    clearMessages,
    resetSession,
    toggleStream,
  }
})
