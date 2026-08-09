/**
 * 用户接口封装（DEMO stub）。
 * 后端端点：GET /api/v1/user/profile
 */
import request from './request'
import type { ApiResponse } from '@/types/chat'
import type { UserProfile } from '@/types/user'

/**
 * 获取用户信息（DEMO 阶段返回固定数据）。
 */
export async function getUserProfile(): Promise<UserProfile> {
  const resp = await request.get<ApiResponse<UserProfile>>('/user/profile')
  return resp.data.data
}
