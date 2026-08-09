/**
 * 请求封装：统一 baseURL / JWT 注入 / 401 处理 / 错误码。
 * 服务端统一响应结构：{ code, message, data }，code===0 为成功。
 */
import Taro from '@tarojs/taro'
import { API_BASE_URL } from '../config/env'
import { useAuthStore } from '../stores/auth'

interface ApiResponse<T = any> {
  code: number
  message: string
  data: T
}

interface RequestOptions {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: Record<string, any>
  auth?: boolean
}

export class ApiError extends Error {
  code: number
  constructor(message: string, code: number) {
    super(message)
    this.code = code
  }
}

export async function request<T = any>(options: RequestOptions): Promise<T> {
  const { url, method = 'GET', data, auth = true } = options
  const header: Record<string, string> = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = useAuthStore.getState().token
    if (token) header.Authorization = `Bearer ${token}`
  }

  const res = await Taro.request<ApiResponse<T>>({
    url: `${API_BASE_URL}${url}`,
    method,
    data,
    header,
    timeout: 60000,
  })

  const body = res.data
  if (body.code !== 0) {
    if (body.code === 401) {
      useAuthStore.getState().logout()
      Taro.navigateTo({ url: '/pages/login/index' })
    }
    throw new ApiError(body.message || '请求失败', body.code)
  }
  return body.data
}

export const http = {
  get: <T = any>(url: string, auth = true) => request<T>({ url, method: 'GET', auth }),
  post: <T = any>(url: string, data?: Record<string, any>, auth = true) =>
    request<T>({ url, method: 'POST', data, auth }),
  put: <T = any>(url: string, data?: Record<string, any>, auth = true) =>
    request<T>({ url, method: 'PUT', data, auth }),
  del: <T = any>(url: string, auth = true) => request<T>({ url, method: 'DELETE', auth }),
}
