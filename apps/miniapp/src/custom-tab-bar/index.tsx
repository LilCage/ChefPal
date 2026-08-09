/**
 * 自定义 TabBar（漫画风，线条 iconfont）。原型 01 底部「百科/厨房/发现/我的」。
 * 订阅 useTabStore.index 高亮当前项；点击 switchTab 切换。
 */
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useTabStore } from '../stores/tab'
import './index.scss'

const TABS = [
  { key: 'home', text: '百科', url: '/pages/index/index' },
  { key: 'kitchen', text: '厨房', url: '/pages/kitchen/index' },
  { key: 'discover', text: '发现', url: '/pages/discover/index' },
  { key: 'mine', text: '我的', url: '/pages/mine/index' },
]

export default function CustomTabBar() {
  const index = useTabStore((s) => s.index)

  const switchTo = (i: number, url: string) => {
    useTabStore.getState().setIndex(i)
    Taro.switchTab({ url })
  }

  return (
    <View className='tab-bar'>
      {TABS.map((tab, i) => (
        <View
          key={tab.key}
          className={`tab-item ${i === index ? 'on' : ''}`}
          onClick={() => switchTo(i, tab.url)}
        >
          <View className={`tab-ic ic ic-${tab.key}${i === index ? '--on' : ''}`} />
          <Text className='tab-label'>{tab.text}</Text>
        </View>
      ))}
    </View>
  )
}
