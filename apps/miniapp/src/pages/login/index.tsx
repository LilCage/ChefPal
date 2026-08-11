/**
 * 屏1 · 微信一键登录（原型 01）
 */
import { Text, View } from '@tarojs/components'
import Taro, { useLoad } from '@tarojs/taro'
import { useState } from 'react'
import { useAuthStore } from '../../stores/auth'
import './index.scss'

export default function Login() {
  const token = useAuthStore((s) => s.token)
  const login = useAuthStore((s) => s.login)
  const [loading, setLoading] = useState(false)

  useLoad(() => {
    if (token) Taro.switchTab({ url: '/pages/index/index' })
  })

  const handleLogin = async () => {
    if (loading) return
    setLoading(true)
    try {
      await login()
      const onboarded = Taro.getStorageSync('chefpal_onboarded')
      if (!onboarded) {
        Taro.reLaunch({ url: '/pages/onboarding/index' })
      } else {
        Taro.switchTab({ url: '/pages/index/index' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '登录失败，请重试', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className='login-bg halftone'>
      <View className='login-content speedlines'>
        <View className='logo-badge'><Text className='logo-emoji'>🍳</Text></View>
        <Text className='login-title pop'>ChefPal</Text>
        <Text className='login-sub'>你的口袋厨师 · 从食材到餐桌</Text>
        <View className='feat-list'>
          <View className='feat'>
            <View className='f-ic'>🍳</View>
            <View className='feat-body'>
              <Text className='feat-t'>冰箱有什么，就做什么</Text>
              <Text className='feat-s'>小伴根据你的食材实时生成专属菜谱</Text>
            </View>
          </View>
          <View className='feat'>
            <View className='f-ic'>✨</View>
            <View className='feat-body'>
              <Text className='feat-t'>怕翻车？小伴手把手教</Text>
              <Text className='feat-s'>核心秘诀 · 分步火候 · 避坑指南</Text>
            </View>
          </View>
          <View className='feat'>
            <View className='f-ic'>🏆</View>
            <View className='feat-body'>
              <Text className='feat-t'>越用越懂你的口味</Text>
              <Text className='feat-s'>忌口 / 辣度 / 咸淡 一键设置</Text>
            </View>
          </View>
        </View>
      </View>
      <View className='login-footer'>
        <View className='btn btn--gold btn--block' onClick={handleLogin}>
          <View className='ic ic-wechat ic-sm' />
          <Text>{loading ? '登录中…' : '微信一键登录'}</Text>
        </View>
        <View className='agree'>
          <Text>登录即代表同意</Text>
          <Text className='agree-link' onClick={() => Taro.navigateTo({ url: '/pages/agreement/index' })}>《用户协议》</Text>
          <Text>与</Text>
          <Text className='agree-link' onClick={() => Taro.navigateTo({ url: '/pages/privacy/index' })}>《隐私政策》</Text>
        </View>
      </View>
    </View>
  )
}
