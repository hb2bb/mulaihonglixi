/**
 * 对话 Pinia store：管理消息列表、会话 ID、发送状态。
 * 组件只调用 action，不直接修改 state。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sendChat } from '@/api/chatApi'
import { useSSE } from '@/hooks/useSSE'
import type { ChatMessage } from '@/types/chat'
import { nowIso } from '@/utils/datetime'

export const useChatStore = defineStore('chat', () => {
  // ---- state ----
  /** 消息列表（单会话） */
  const messages = ref<ChatMessage[]>([])
  /** 当前会话 ID，首次为 null */
  const sessionId = ref<string | null>(null)
  /** 是否正在发送/接收中 */
  const isSending = ref(false)
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

  // ---- actions ----

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

    try {
      if (useStream.value) {
        sendStream({ message: trimmed, session_id: sessionId.value })
      } else {
        const data = await sendChat({ message: trimmed, session_id: sessionId.value })
        sessionId.value = data.session_id
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
    errorMessage,
    useStream,
    isStreaming,
    // actions
    sendMessage,
    clearMessages,
    resetSession,
    toggleStream,
  }
})
