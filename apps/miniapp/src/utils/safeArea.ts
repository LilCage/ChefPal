/**
 * 顶部安全区工具。
 * navigationStyle: 'custom' 后，env(safe-area-inset-top) 在开发者工具/部分机型不生效，
 * 改用运行时读取 statusBarHeight（物理 px）作为导航栏上边距，避免内容被刘海/状态栏遮挡。
 */
import Taro from '@tarojs/taro'

let cached: number | null = null

/** 返回导航栏应有的 padding-top（物理 px）= 状态栏高 + 8px 余量 */
export function getSafeTop(): number {
  if (cached == null) {
    try {
      const info = Taro.getSystemInfoSync()
      cached = (info.statusBarHeight || 20) + 8
    } catch {
      cached = 28
    }
  }
  return cached
}
