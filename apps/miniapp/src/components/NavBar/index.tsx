/**
 * 顶部导航：返回按钮 + 居中标题 + 右侧操作。
 */
import { ReactNode } from 'react'
import Taro from '@tarojs/taro'
import { View } from '@tarojs/components'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

interface NavBarProps {
  title?: ReactNode
  showBack?: boolean
  right?: ReactNode
  onBack?: () => void
}

export default function NavBar({ title, showBack, right, onBack }: NavBarProps) {
  const handleBack = () => {
    if (onBack) return onBack()
    Taro.navigateBack({ delta: 1 }).catch(() => Taro.switchTab({ url: '/pages/index/index' }))
  }
  return (
    <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
      <View className='nav-side'>
        {showBack && (
          <View className='nbtn' onClick={handleBack}>
            <View className='ic ic-back ic-sm' />
          </View>
        )}
      </View>
      <View className='nav-title'>{title}</View>
      <View className='nav-side nav-side--right'>{right}</View>
    </View>
  )
}
