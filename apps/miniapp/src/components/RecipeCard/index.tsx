/**
 * 菜谱卡：名称 + 匹配度能量条 + 时间/难度/缺料。
 * 对齐原型 01 屏3 的 .r-card。
 */
import type { ReactNode } from 'react'
import { Text, View } from '@tarojs/components'
import './index.scss'

interface RecipeCardProps {
  name: string
  matchScore: number
  timeMinutes: number
  difficulty: string
  style?: string
  missing?: string[]
  emoji?: string
  wide?: boolean
  /** 隐藏匹配度百分比徽章与能量条（收藏页知识库菜匹配度无含义；顶部图片区留给成品图） */
  hideMatch?: boolean
  /** 菜名行右侧操作区（如"取消收藏"按钮），右对齐、不占单独一行 */
  action?: ReactNode
  onClick?: () => void
}

export default function RecipeCard({
  name,
  matchScore,
  timeMinutes,
  difficulty,
  style = '',
  missing = [],
  emoji = '🍜',
  wide,
  hideMatch,
  action,
  onClick,
}: RecipeCardProps) {
  return (
    <View className={`r-card ${wide ? 'wide' : ''}`} onClick={onClick}>
      <View className='r-img'>
        <Text userSelect className='r-emoji'>{emoji}</Text>
        {!hideMatch && <View className='deg'>{matchScore}%</View>}
        {style && <View className='style-badge'><Text userSelect>{style}</Text></View>}
      </View>
      <View className='r-name'><Text userSelect className='r-name-text'>{name}</Text></View>
      <View className='r-meta'>
        {timeMinutes > 0 && <View className='mini-chip'><Text userSelect>⏱ {timeMinutes}分钟</Text></View>}
        <View className='mini-chip'><Text userSelect>{difficulty}</Text></View>
        {missing.length > 0 && <View className='mini-chip red'><Text userSelect>缺:{missing[0]}</Text></View>}
      </View>
      {!hideMatch && (
        <View className='energy matched'>
          <View className='energy-fill' style={{ width: `${matchScore}%` }} />
        </View>
      )}
      {action && <View className='r-action'>{action}</View>}
    </View>
  )
}
