/**
 * 空状态：原型 02 屏5。
 */
import { Text, View } from '@tarojs/components'
import './index.scss'

interface EmptyStateProps {
  icon?: string
  title: string
  desc?: string
  btnText?: string
  onBtn?: () => void
}

export default function EmptyState({ icon = '🍳', title, desc, btnText, onBtn }: EmptyStateProps) {
  return (
    <View className='empty'>
      <View className='empty-art'><Text userSelect>{icon}</Text></View>
      <Text userSelect className='empty-title'>{title}</Text>
      {desc && <Text userSelect className='empty-desc'>{desc}</Text>}
      {btnText && onBtn && (
        <View className='btn btn--red btn--block' onClick={onBtn}>
          <Text userSelect>{btnText}</Text>
        </View>
      )}
    </View>
  )
}
