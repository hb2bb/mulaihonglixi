/**
 * 对话相关 TypeScript 类型定义。
 * 对齐后端 schemas/request/chat.py 与 schemas/response/chat.py。
 */

/** 消息角色 */
type ChatRole = 'user' | 'assistant'

/** 单条聊天消息（前端展示用） */
interface ChatMessage {
  /** 消息角色 */
  role: ChatRole
  /** 消息内容 */
  content: string
  /** 时间戳 ISO8601 */
  datetime: string
  /** 是否正在流式接收中（assistant 消息专用） */
  streaming?: boolean
}

/** POST /api/v1/chat 请求参数 */
interface ChatSendParams {
  /** 用户消息内容 */
  message: string
  /** 会话 ID，首次为 null */
  session_id: string | null
}

/** POST /api/v1/chat 响应 data */
interface ChatReplyData {
  /** 会话 ID */
  session_id: string
  /** 回复内容 */
  reply: string
  /** 时间戳 ISO8601 */
  datetime: string
}

/** 统一响应结构 */
interface ApiResponse<T = unknown> {
  /** 业务码，0 成功 */
  code: number
  /** 提示信息 */
  msg: string
  /** 业务数据 */
  data: T
}

/** SSE 流式事件 payload */
interface ChatStreamChunk {
  /** 单个 chunk 文本 */
  chunk?: string
  /** 是否结束 */
  done?: boolean
  /** 完整回复（done=true 时） */
  reply?: string
  /** 会话 ID（done=true 时） */
  session_id?: string
  /** 时间戳（done=true 时） */
  datetime?: string
  /** 错误信息 */
  error?: string
}

export type {
  ChatRole,
  ChatMessage,
  ChatSendParams,
  ChatReplyData,
  ApiResponse,
  ChatStreamChunk,
}
