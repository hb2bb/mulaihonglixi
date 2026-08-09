/**
 * 对话接口封装。
 * 后端端点：
 *   POST /api/v1/chat          非流式对话
 *   GET  /api/v1/chat/stream   流式对话（SSE）
 */
import request from './request'
import type { ApiResponse, ChatReplyData, ChatSendParams } from '@/types/chat'

/**
 * 非流式对话：发送消息并等待完整回复。
 * @param params message + session_id
 * @returns ChatReplyData { session_id, reply, datetime }
 */
export async function sendChat(params: ChatSendParams): Promise<ChatReplyData> {
  const resp = await request.post<ApiResponse<ChatReplyData>>('/chat', params)
  return resp.data.data
}

/**
 * 流式对话回调签名。
 */
interface StreamCallbacks {
  onChunk: (chunk: string) => void
  onDone: (data: ChatReplyData) => void
  onError: (msg: string) => void
}

/**
 * 流式对话：通过 EventSource 监听 SSE。
 * @param params message + session_id
 * @param callbacks onChunk / onDone / onError
 * @returns 关闭函数，调用以主动断开
 */
export function streamChat(
  params: ChatSendParams,
  callbacks: StreamCallbacks
): () => void {
  const { message, session_id } = params
  // EventSource 只支持 GET，参数走 query
  const url = new URL('/api/v1/chat/stream', window.location.origin)
  url.searchParams.set('message', message)
  if (session_id) {
    url.searchParams.set('session_id', session_id)
  }

  const es = new EventSource(url.toString())

  es.onmessage = (event: MessageEvent) => {
    try {
      const payload = JSON.parse(event.data) as { chunk?: string; done?: boolean; reply?: string; session_id?: string; datetime?: string; error?: string }
      if (payload.error) {
        callbacks.onError(payload.error)
        es.close()
        return
      }
      if (payload.done && payload.reply) {
        callbacks.onDone({
          session_id: payload.session_id || session_id || '',
          reply: payload.reply,
          datetime: payload.datetime || '',
        })
        es.close()
        return
      }
      if (payload.chunk) {
        callbacks.onChunk(payload.chunk)
      }
    } catch (err) {
      callbacks.onError(`SSE 解析失败: ${err}`)
      es.close()
    }
  }

  es.onerror = () => {
    callbacks.onError('SSE 连接异常')
    es.close()
  }

  // 返回关闭函数
  return () => es.close()
}
