/**
 * Axios 实例封装：baseURL、超时、请求/响应拦截器、错误统一处理。
 * 仅在此处初始化，业务模块通过 @/api/xxxApi 调用。
 */
import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import type { ApiResponse } from '@/types/chat'

const request: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器：可在此附加 Authorization 鉴权头
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // DEMO 阶段无鉴权，预留位置
    // const token = localStorage.getItem('token')
    // if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：统一处理业务码与 HTTP 错误
request.interceptors.response.use(
  (response) => {
    const data = response.data as ApiResponse
    // 业务码非 0 -> 业务错误
    if (data.code !== 0) {
      console.error(`[API] business error: code=${data.code} msg=${data.msg}`)
      return Promise.reject(new Error(data.msg || '业务错误'))
    }
    return response
  },
  (error: AxiosError) => {
    // HTTP 错误统一处理
    if (error.response) {
      const status = error.response.status
      if (status === 401) {
        console.error('[API] 401 未授权，跳转登录')
        // 未来：router.push('/login')
      } else if (status >= 500) {
        console.error('[API] 服务端错误', status)
      }
    } else if (error.code === 'ECONNABORTED') {
      console.error('[API] 请求超时')
    }
    return Promise.reject(error)
  }
)

export default request
