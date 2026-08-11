/**
 * 问答历史（原型 02 屏3）：最近 20 条 · 可删除 · 点击展开详情（气泡在左上角指向问题）
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
  const [expandedId, setExpandedId] = useState<string | null>(null) // 当前展开的记录 id

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
      if (expandedId === id) setExpandedId(null)
    } catch (e: any) {
      Taro.showToast({ title: e.message, icon: 'none' })
    }
  }

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id))

  /* 完整答案正文（多菜推荐 或 单菜秘诀/食材/步骤/避坑） */
  const renderAnswerBody = (rec: QARecord) => {
    const ans = rec.answer
    if (ans.recommendations) {
      return (
        <View className='h-rec'>
          {ans.recommendations.map((r, i) => (
            <View key={i} className='h-rec-item'>
              <View className='h-rec-head'>
                <Text className='h-rec-no'>{i + 1}</Text>
                <Text className='h-rec-name'>{r.name}</Text>
                {r.time_minutes > 0 && <View className='mini-chip'><Text>⏱ {r.time_minutes}分钟</Text></View>}
              </View>
              <Text className='h-rec-secret' userSelect>{r.core_secret}</Text>
              {r.ingredients.length > 0 && (
                <Text className='h-rec-ings' userSelect>食材：{r.ingredients.join('、')}</Text>
              )}
            </View>
          ))}
        </View>
      )
    }
    return (
      <View className='h-ans'>
        <Text className='h-secret' userSelect>{ans.core_secret}</Text>
        {ans.ingredients.length > 0 && (
          <>
            <Text className='h-label'>食材清单</Text>
            <Text className='h-ings' userSelect>{ans.ingredients.join('、')}</Text>
          </>
        )}
        {ans.steps.length > 0 && (
          <>
            <Text className='h-label'>烹饪步骤</Text>
            <View className='h-steps'>
              {ans.steps.map((s, i) => (
                <View key={i} className='h-step'><Text className='h-step-no'>{i + 1}</Text><Text userSelect>{s}</Text></View>
              ))}
            </View>
          </>
        )}
        {ans.avoid_pitfalls.length > 0 && (
          <>
            <Text className='h-label'>避坑指南</Text>
            {ans.avoid_pitfalls.map((p, i) => (
              <View key={i} className='h-pit'>⚠ <Text userSelect>{p}</Text></View>
            ))}
          </>
        )}
      </View>
    )
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
      <NavBar title='问答历史' showBack />

      <View className='his-list'>
        {records.map((r) => (
          <View key={r.id} className='his-block'>
            <View className='his-item' onClick={() => toggle(r.id)}>
              <View className='q-badge'><Text>Q</Text></View>
              <View className='htext'>
                <Text className='hq'>{r.question}</Text>
                <Text className='htime'>{formatTime(r.created_at)}</Text>
              </View>
              <View className='ic ic-trash ic-sm' onClick={(e) => { e.stopPropagation(); remove(r.id) }} />
            </View>
            {/* 点击问题 → 展开完整问答（气泡在左上角指向问题） */}
            {expandedId === r.id && (
              <View className='his-detail'>
                {renderAnswerBody(r)}
              </View>
            )}
          </View>
        ))}
      </View>

      {records.length === 0 && (
        <View className='note note--center'>暂无问答记录，去首页问小伴一个问题吧</View>
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
