/**
 * 菜谱卡：名称 + 匹配度能量条 + 时间/难度/缺料。
 * 对齐原型 01 屏3 的 .r-card。
 */
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
  onClick,
}: RecipeCardProps) {
  return (
    <View className={`r-card ${wide ? 'wide' : ''}`} onClick={onClick}>
      <View className='r-img'>
        <Text className='r-emoji'>{emoji}</Text>
        <View className='deg'>{matchScore}%</View>
        {style && <View className='style-badge'><Text>{style}</Text></View>}
      </View>
      <View className='r-name'>{name}</View>
      <View className='r-meta'>
        <View className='mini-chip'><Text>⏱ {timeMinutes}分钟</Text></View>
        <View className='mini-chip'><Text>{difficulty}</Text></View>
        {missing.length > 0 && <View className='mini-chip red'><Text>缺:{missing[0]}</Text></View>}
      </View>
      <View className='energy matched'>
        <View className='energy-fill' style={{ width: `${matchScore}%` }} />
      </View>
    </View>
  )
}
