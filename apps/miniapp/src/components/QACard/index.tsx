/**
 * 问答卡片：Q 徽章 + 问题 + 摘要 + 收藏星标 + 时间。
 * 对齐原型 01 屏2 / 02 屏1 的 .qa-card。
 */
import { Text, View } from '@tarojs/components'
import './index.scss'

interface QACardProps {
  question: string
  summary?: string
  time?: string
  starred?: boolean
  onClick?: () => void
}

export default function QACard({ question, summary, time, starred, onClick }: QACardProps) {
  return (
    <View className='qa-card' onClick={onClick}>
      <View className='qa-q'>
        <View className='q-badge'>Q</View>
        <Text userSelect className='qa-question'>{question}</Text>
        {starred && <View className='ic ic-star--on ic-sm' />}
        {time && <Text userSelect className='qa-time'>{time}</Text>}
      </View>
      {summary && <Text userSelect className='qa-a'>{summary}</Text>}
    </View>
  )
}
