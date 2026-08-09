/**
 * 屏2 · 首页 AI 烹饪百科（原型 01）
 * 搜索框 + 猜你想问 + 今日AI秘技 + 问答历史 + 收藏问答
 */
import { Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import QACard from '../../components/QACard'
import { addFavorite, askQA, fetchQAHistory, type QARecord } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
import { useTabStore } from '../../stores/tab'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const HOT_QUESTIONS = ['红烧肉不腻', '蒸蛋怎么才嫩', '炖肉去腥', '剩菜大变身', '煎鱼不破皮', '青菜不变色']

export default function Index() {
  const setTab = useTabStore((s) => s.setIndex)
  const [keyword, setKeyword] = useState('')
  const [current, setCurrent] = useState<QARecord | null>(null)
  const [history, setHistory] = useState<QARecord[]>([])
  const [loading, setLoading] = useState(false)

  useDidShow(() => {
    setTab(0)
    // 未登录不发起鉴权请求，直接去登录页
    if (!useAuthStore.getState().token) {
      Taro.reLaunch({ url: '/pages/login/index' })
      return
    }
    loadHistory()
  })

  const loadHistory = async () => {
    try {
      setHistory(await fetchQAHistory())
    } catch {
      /* 未登录/网络问题静默 */
    }
  }

  const ask = async (q: string) => {
    const question = (q || keyword).trim()
    if (!question) return
    setLoading(true)
    try {
      const rec = await askQA(question)
      setCurrent(rec)
      await loadHistory()
    } catch (e: any) {
      Taro.showToast({ title: e.message || '提问失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const saveFavorite = async (rec: QARecord) => {
    try {
      await addFavorite('qa', rec.id)
      Taro.showToast({ title: '已收藏到「我的收藏」', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e.message, icon: 'none' })
    }
  }

  return (
    <View className='page-content home'>
      {/* 顶部导航 */}
      <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
        <View className='nav-title'><Text className='pop'>ChefPal</Text> 美食百科</View>
      </View>

      <View className='searchbar'>
        <View className='ic ic-search' />
        <Input
          className='search-input'
          value={keyword}
          placeholder='问 AI：红烧肉怎么做不腻？'
          confirmType='search'
          onInput={(e) => setKeyword(e.detail.value)}
          onConfirm={() => ask(keyword)}
        />
        <View className='sbtn' onClick={() => ask(keyword)}><View className='ic ic-search--white ic-sm' /></View>
      </View>

      <View className='section'>
        <View className='sec-title'>⚡ 猜你想问</View>
        <View className='chips'>
          {HOT_QUESTIONS.map((q, i) => (
            <View key={q} className={`chip ${i === 0 ? 'chip--hot' : ''}`} onClick={() => ask(q)}>
              <Text>{q}</Text>
            </View>
          ))}
        </View>
      </View>

      <View className='section'>
        <View className='sec-title'>
          🔥 今日 AI 秘技
          {current && (
            <View className='more' onClick={() => ask(current.question)}>重新生成</View>
          )}
        </View>
      </View>

      {loading ? (
        <View className='thinking bubble'><Text>🤖 AI 正在联网搜索并思考…</Text></View>
      ) : current ? (
        <View className='bubble qa-answer'>
          <View className='qa-ans-head'>
            <Text className='qa-ans-q'>{current.question}</Text>
            <View className='star-burst star-burst--mini'>核心秘诀</View>
          </View>
          <Text className='qa-ans-secret'>{current.answer.core_secret}</Text>
          <Text className='qa-ans-label'>烹饪步骤</Text>
          <View className='qa-ans-steps'>
            {current.answer.steps.map((s, i) => (
              <View key={i} className='qa-step'><Text className='qa-step-no'>{i + 1}</Text><Text>{s}</Text></View>
            ))}
          </View>
          {current.answer.avoid_pitfalls.length > 0 && (
            <>
              <Text className='qa-ans-label'>避坑指南</Text>
              {current.answer.avoid_pitfalls.map((p, i) => (
                <View key={i} className='qa-pit'>⚠ {p}</View>
              ))}
            </>
          )}
          <View className='qa-ans-actions'>
            <View className='btn btn--white btn--xs' onClick={() => saveFavorite(current)}>
              <View className='ic ic-star ic-sm' />
              <Text>收藏</Text>
            </View>
          </View>
        </View>
      ) : (
        <View className='bubble tip-empty'>
          <Text>💡 输入一个厨艺问题，AI 会联网搜索并给出核心秘诀、步骤与避坑指南</Text>
        </View>
      )}

      <View className='section'>
        <View className='sec-title'>📚 我的问答历史</View>
      </View>
      {history.map((h) => (
        <QACard key={h.id} question={h.question} summary={`核心秘诀：${h.answer.core_secret}`} />
      ))}
      {history.length === 0 && !loading && (
        <View className='note note--center'>还没有提问，问 AI 一个问题吧</View>
      )}
    </View>
  )
}
