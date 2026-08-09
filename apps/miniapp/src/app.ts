import { PropsWithChildren } from 'react'
import Taro, { useLaunch } from '@tarojs/taro'
import { useAuthStore } from './stores/auth'
import './styles/theme.scss'
import './styles/icons.scss'
import './styles/brandfont.scss'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // 启动时从本地缓存恢复登录态
    useAuthStore.getState().hydrate()
    // 未登录 → 首屏直接去登录页，避免 tab 页未授权请求 401
    if (!useAuthStore.getState().token) {
      Taro.reLaunch({ url: '/pages/login/index' })
    }
  })

  return children
}

export default App
