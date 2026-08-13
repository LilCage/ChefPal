/**
 * 历史对话（会话列表）：最近 20 个会话 · 可删除 · 点某会话 → 恢复回首页继续对话。
 * 会话内完整多轮对话由首页加载（storage 切 session_id → 首页 useDidShow 自动恢复）。
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import { deleteQASession, fetchQASessions, type QASessionSummary } from '../../services/api'
import './index.scss'

const SESSION_KEY = 'chefpal_session_id'

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
  const [sessions, setSessions] = useState<QASessionSummary[]>([])

  useDidShow(() => load())

  const load = async () => {
    try {
      setSessions(await fetchQASessions())
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    }
  }

  /* 点某会话 → 设 storage → 回首页（首页 useDidShow 自动加载该会话完整多轮对话，可继续聊） */
  const openSession = (s: QASessionSummary) => {
    Taro.setStorageSync(SESSION_KEY, s.session_id)
    Taro.switchTab({ url: '/pages/index/index' })
  }

  const remove = async (s: QASessionSummary) => {
    try {
      await deleteQASession(s.session_id)
      setSessions((prev) => prev.filter((x) => x.session_id !== s.session_id))
    } catch (e: any) {
      Taro.showToast({ title: e.message, icon: 'none' })
    }
  }

  const clearAll = () => {
    Taro.showModal({
      title: '清空全部历史',
      content: '将删除最近的所有历史对话，确定吗？',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        for (const s of [...sessions]) await remove(s)
        Taro.showToast({ title: '已清空', icon: 'none' })
      },
    })
  }

  return (
    <View className='page-content qah'>
      <NavBar title='历史对话' showBack />

      <View className='his-list'>
        {sessions.map((s) => (
          <View key={s.session_id} className='his-block'>
            <View className='his-item' onClick={() => openSession(s)}>
              <View className='q-badge'><Text userSelect>{s.msg_count}</Text></View>
              <View className='htext'>
                <Text className='hq'>{s.title || s.last_question}</Text>
                <Text className='htime'>
                  {formatTime(s.last_at)}
                  {s.msg_count > 1 ? ` · ${s.msg_count} 轮` : ''}
                </Text>
              </View>
              <View className='ic ic-trash ic-sm' onClick={(e) => { e.stopPropagation(); remove(s) }} />
            </View>
          </View>
        ))}
      </View>

      {sessions.length === 0 && (
        <View className='note note--center'>暂无历史对话，去首页问小伴一个问题吧</View>
      )}

      {sessions.length > 0 && (
        <View className='clear-wrap'>
          <View className='btn btn--white btn--block' onClick={clearAll}>
            <Text userSelect>清空全部历史</Text>
          </View>
          <Text className='note note--center'>最多展示最近 20 个对话</Text>
        </View>
      )}
    </View>
  )
}
