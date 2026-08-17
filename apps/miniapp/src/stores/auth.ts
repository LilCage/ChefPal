/**
 * 登录态 Store（Zustand）。token 持久化到本地缓存，启动时 hydrate 恢复。
 */
import { create } from 'zustand'
import Taro from '@tarojs/taro'
import { login as apiLogin } from '../services/api'

const TOKEN_KEY = 'chefpal_token'
const USER_KEY = 'chefpal_user'

export interface User {
  id: string
  nickname?: string | null
  avatar_url?: string | null
  preferences: Record<string, any>
  /** 是否已看过新用户引导（服务端随账号存储，避免本地缓存被清重复引导） */
  onboarded?: boolean
  created_at?: string
}

interface AuthState {
  token: string | null
  user: User | null
  login: () => Promise<void>
  logout: () => void
  hydrate: () => void
  setUser: (user: User) => void
  updatePreferences: (prefs: Partial<Record<string, any>>) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,

  login: async () => {
    const { code } = await Taro.login()
    const data = await apiLogin(code)
    set({ token: data.token, user: data.user })
    Taro.setStorageSync(TOKEN_KEY, data.token)
    Taro.setStorageSync(USER_KEY, data.user)
  },

  logout: () => {
    set({ token: null, user: null })
    Taro.removeStorageSync(TOKEN_KEY)
    Taro.removeStorageSync(USER_KEY)
  },

  hydrate: () => {
    const token = Taro.getStorageSync(TOKEN_KEY)
    const user = Taro.getStorageSync(USER_KEY)
    if (token) set({ token, user: user || null })
  },

  setUser: (user) => {
    set({ user })
    Taro.setStorageSync(USER_KEY, user)
  },

  updatePreferences: (prefs) => {
    const user = get().user
    if (!user) return
    const next = { ...user, preferences: { ...user.preferences, ...prefs } }
    set({ user: next })
    Taro.setStorageSync(USER_KEY, next)
  },
}))
