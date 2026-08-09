/**
 * SSE 流式对话组合式 Hook：封装 EventSource 生命周期与状态管理。
 * 统一处理重连、销毁逻辑，组件按需调用。
 */
import { ref, onUnmounted } from 'vue'
import { streamChat } from '@/api/chatApi'
import type { ChatReplyData, ChatSendParams } from '@/types/chat'

interface UseSSEOptions {
  onChunk: (chunk: string) => void
  onDone: (data: ChatReplyData) => void
  onError: (msg: string) => void
}

/**
 * SSE 流式对话 Hook。
 * @returns isStreaming 状态 + sendStream 发起函数 + closeStream 关闭函数
 */
export function useSSE(options: UseSSEOptions) {
  const isStreaming = ref(false)
  let closeFn: (() => void) | null = null

  /**
   * 发起流式对话。
   * @param params message + session_id
   */
  function sendStream(params: ChatSendParams): void {
    // 若已有连接，先关闭
    if (closeFn) {
      closeFn()
    }
    isStreaming.value = true
    closeFn = streamChat(params, {
      onChunk: options.onChunk,
      onDone: (data) => {
        isStreaming.value = false
        closeFn = null
        options.onDone(data)
      },
      onError: (msg) => {
        isStreaming.value = false
        closeFn = null
        options.onError(msg)
      },
    })
  }

  /**
   * 主动关闭流。
   */
  function closeStream(): void {
    if (closeFn) {
      closeFn()
      closeFn = null
    }
    isStreaming.value = false
  }

  // 组件卸载时自动清理
  onUnmounted(() => {
    closeStream()
  })

  return { isStreaming, sendStream, closeStream }
}
