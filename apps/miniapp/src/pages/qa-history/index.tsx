/**
 * 问答历史（原型 02 屏3）：最近 20 条 · 可删除
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { deleteQARecord, fetchQAHistory, type QARecord } from '../../services/api'
import './index.scss'

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const pad = (n: number) => String(n).padStart(2, '0')
  if (sameDay) return `今天 ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function QAHistory() {
  const [records, setRecords] = useState<QARecord[]>([])

  useDidShow(() => load())

  const load = async () => {
    try {
      setRecords(await fetchQAHistory())
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  const remove = async (id: string) => {
    try {
      await deleteQARecord(id)
      setRecords(records.filter((r) => r.id !== id))
    } catch (e: any) {
      Taro.showToast({ title: e.message, icon: 'none' })
    }
  }

  const clearAll = () => {
    Taro.showModal({
      title: '清空全部历史',
      content: '将删除最近的所有问答记录，确定吗？',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        for (const rec of [...records]) await remove(rec.id)
        Taro.showToast({ title: '已清空', icon: 'none' })
      },
    })
  }

  return (
    <View className='page-content qah'>
      <NavBar
        title='问答历史'
        showBack
        right={<View className='txtbtn' onClick={clearAll}><Text>清空</Text></View>}
      />

      <View className='his-list'>
        {records.map((r) => (
          <View key={r.id} className='his-item'>
            <View className='q-badge'><Text>Q</Text></View>
            <View className='htext'>
              <Text className='hq'>{r.question}</Text>
              <Text className='htime'>{formatTime(r.created_at)}</Text>
            </View>
            <View className='ic ic-trash ic-sm' onClick={() => remove(r.id)} />
          </View>
        ))}
      </View>

      {records.length === 0 && (
        <View className='note note--center'>暂无问答记录，去首页问 AI 一个问题吧</View>
      )}

      {records.length > 0 && (
        <View className='clear-wrap'>
          <View className='btn btn--white btn--block' onClick={clearAll}>
            <Text>清空全部历史</Text>
          </View>
          <Text className='note note--center'>最多保留最近 20 条问答记录</Text>
        </View>
      )}
    </View>
  )
}
