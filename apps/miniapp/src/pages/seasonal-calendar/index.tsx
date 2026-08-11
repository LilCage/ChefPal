/**
 * 时令食材日历（原型 05 屏3）：月份切换 + 当季食材网格 + 当季推荐
 * 数据源 GET /seasonal?month=N（纯静态，无 AI 调用）
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { fetchSeasonal, type SeasonalData } from '../../services/api'
import './index.scss'

export default function SeasonalCalendar() {
  const [month, setMonth] = useState<number>(new Date().getMonth() + 1)
  const [data, setData] = useState<SeasonalData | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async (m: number) => {
    if (loading) return
    setLoading(true)
    try {
      const d = await fetchSeasonal(m)
      setData(d)
      setMonth(d.month)
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  useDidShow(() => {
    load(month)
  })

  const prev = () => {
    const m = month === 1 ? 12 : month - 1
    setMonth(m)
    load(m)
  }
  const next = () => {
    const m = month === 12 ? 1 : month + 1
    setMonth(m)
    load(m)
  }

  return (
    <View className='page-content seasonal'>
      <NavBar title={<Text userSelect className='pop'>时令食材</Text>} showBack />

      <View className='month-bar'>
        <View className='arrow' onClick={prev}>
          <View className='ic ic-chev-l ic-sm' />
        </View>
        <Text userSelect className='month-label'>{data?.label || `${month} 月`}</Text>
        <View className='arrow' onClick={next}>
          <View className='ic ic-chev-r ic-sm' />
        </View>
      </View>

      <View className='season-grid'>
        {(data?.items || []).map((item) => (
          <View key={item.name} className='season-item'>
            <Text userSelect className='s-emoji'>{item.emoji}</Text>
            <Text userSelect className='s-name'>{item.name}</Text>
            <View className={`s-badge ${item.level === '应季' ? 'best' : 'ok'}`}>
              <Text userSelect>{item.level}</Text>
            </View>
            <Text userSelect className='s-note'>{item.note}</Text>
          </View>
        ))}
      </View>

      <View className='sec'>
        <View className='sec-title'>🍽 当季推荐</View>
      </View>

      {data?.pairing && (
        <View className='bubble'>
          <View className='star-burst'>
            <Text userSelect>食材猎人推荐</Text>
          </View>
          <View className='pair-title'>
            <Text userSelect>
              {data.pairing.ingredients.map((ing) => ` ${ing}`).join(' +')} →{' '}
              <Text userSelect className='pair-dish'>{data.pairing.dish}</Text>
            </Text>
          </View>
          <Text userSelect className='note'>{data.pairing.note}</Text>
        </View>
      )}

      {loading && <Text userSelect className='note season-note'>加载中…</Text>}
    </View>
  )
}
