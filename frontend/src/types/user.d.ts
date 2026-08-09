/**
 * 用户相关 TypeScript 类型定义（DEMO stub）。
 */

/** GET /api/v1/user/profile 响应 data */
interface UserProfile {
  user_id: string
  nickname: string
  avatar: string
}

export type { UserProfile }
