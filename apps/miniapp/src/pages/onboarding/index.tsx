/**
 * 新用户引导（原型 02 屏6）：学 · 做 · 晒，首次登录展示一次
 */
import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const ONBOARDED_KEY = 'chefpal_onboarded'

const CARDS = [
  { icon: 'ic-search', title: '学 · 问小伴学厨艺', sub: '核心秘诀 + 避坑指南，结构化讲解' },
  { icon: 'ic-kitchen', title: '做 · 食材魔方变好菜', sub: '冰箱有什么就做什么，小伴实时生成' },
  { icon: 'ic-discover', title: '晒 · 社区分享作品', sub: '跟做打卡，收获点赞与鼓励' },
]

export default function Onboarding() {
  const finish = () => {
    Taro.setStorageSync(ONBOARDED_KEY, true)
    // 延迟跳转：避免 setStorageSync 后立即 switchTab，触发渲染层「first rendering data」竞态
    setTimeout(() => Taro.switchTab({ url: '/pages/index/index' }), 50)
  }

  return (
    <View className='onboard-bg halftone'>
      <View className='onboard-content speedlines' style={{ paddingTop: `${getSafeTop() + 48}px` }}>
        <View className='logo-badge'>
          <View className='ic ic-kitchen ic-lg' />
        </View>
        <Text userSelect className='onboard-title'>欢迎来到美食猎人的世界</Text>
        <Text userSelect className='onboard-sub'>把冰箱变成你的食材猎场 🗺</Text>

        <View className='ob-cards'>
          {CARDS.map((c) => (
            <View key={c.title} className='ob-card'>
              <View className='ob-ic'><View className={`ic ${c.icon} ic-sm`} /></View>
              <View className='ob-body'>
                <Text userSelect className='ob-t'>{c.title}</Text>
                <Text userSelect className='ob-s'>{c.sub}</Text>
              </View>
            </View>
          ))}
        </View>

        <View className='ob-dots'>
          <View className='ob-dot on' />
          <View className='ob-dot' />
          <View className='ob-dot' />
        </View>
      </View>

      <View className='onboard-footer'>
        <View className='btn btn--gold btn--block' onClick={finish}>
          <Text userSelect>开始我的美食之旅</Text>
        </View>
        <Text userSelect className='ob-skip' onClick={finish}>跳过</Text>
      </View>
    </View>
  )
}
