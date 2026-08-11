/**
 * 屏2 · 首页 AI 烹饪百科（原型 01）
 * 搜索框 + 猜你想问 + 今日AI秘技 + 问答历史 + 收藏问答
 */
import { Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import QACard from '../../components/QACard'
import { addFavorite, askQA, deleteQARecord, fetchQAHistory, type QARecord } from '../../services/api'
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
  /* 猜你想问浮层：点击输入框弹出，点某条直接问 */
  const [showSuggest, setShowSuggest] = useState(false)

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

  const removeHistory = (id: string) => {
    Taro.showModal({
      title: '删除这条问答',
      content: '确定删除这条问答历史吗？',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await deleteQARecord(id)
          setHistory((prev) => prev.filter((h) => h.id !== id))
          Taro.showToast({ title: '已删除', icon: 'none' })
        } catch (e: any) {
          Taro.showToast({ title: e.message || '删除失败', icon: 'none' })
        }
      },
    })
  }

  return (
    <View className='page-content home'>
      {/* 顶部导航 */}
      <View className='nav' style={{ paddingTop: `${getSafeTop()}px` }}>
        <View className='nav-title'><Text className='pop'>ChefPal</Text> 美食百科</View>
      </View>

      <View className='searchbar'>
        <Textarea
          className='search-input'
          value={keyword}
          placeholder='问 AI：输入你的厨艺问题'
          placeholderClass='search-ph'
          autoHeight
          maxlength={500}
          onFocus={() => { if (!keyword.trim()) setShowSuggest(true) }}
          onInput={(e) => {
            setKeyword(e.detail.value)
            if (e.detail.value.trim()) setShowSuggest(false)
          }}
          onBlur={() => setTimeout(() => setShowSuggest(false), 200)}
          onConfirm={() => ask(keyword)}
        />
        <View className={`sbtn ${keyword.trim() ? '' : 'sbtn--idle'}`} onClick={() => ask(keyword)}>
          <View className='ic ic-search--white ic-sm' />
        </View>
      </View>

      {/* 猜你想问浮层：点击输入框弹出，点某条直接问 */}
      {showSuggest && (
        <View className='suggest'>
          <View className='suggest-head'>
            <Text className='suggest-title'>⚡ 猜你想问</Text>
            <View className='suggest-close' onClick={() => setShowSuggest(false)}><Text>收起 ×</Text></View>
          </View>
          <View className='suggest-chips'>
            {HOT_QUESTIONS.map((q) => (
              <View key={q} className='chip' onClick={() => { setShowSuggest(false); ask(q) }}>
                <Text>{q}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

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
            {!current.answer.recommendations && (
              <View className='star-burst star-burst--mini'>{current.answer.dish_name || '核心秘诀'}</View>
            )}
          </View>

          {/* 类型二 · 多菜推荐 */}
          {current.answer.recommendations ? (
            <View className='qa-recs'>
              {current.answer.recommendations.map((r, i) => (
                <View key={i} className='rec-card'>
                  <View className='rec-head'>
                    <Text className='rec-no'>{i + 1}</Text>
                    <Text className='rec-name'>{r.name}</Text>
                    {r.time_minutes > 0 && <View className='mini-chip'><Text>⏱ {r.time_minutes}分钟</Text></View>}
                  </View>
                  <Text className='rec-secret'>{r.core_secret}</Text>
                  {r.ingredients.length > 0 && (
                    <Text className='rec-ings'>食材：{r.ingredients.join('、')}</Text>
                  )}
                </View>
              ))}
            </View>
          ) : (
            <>
              <Text className='qa-ans-secret'>{current.answer.core_secret}</Text>
              {current.answer.ingredients.length > 0 && (
                <>
                  <Text className='qa-ans-label'>食材清单</Text>
                  <Text className='qa-ans-ings'>{current.answer.ingredients.join('、')}</Text>
                </>
              )}
              {current.answer.steps.length > 0 && (
                <>
                  <Text className='qa-ans-label'>烹饪步骤</Text>
                  <View className='qa-ans-steps'>
                    {current.answer.steps.map((s, i) => (
                      <View key={i} className='qa-step'><Text className='qa-step-no'>{i + 1}</Text><Text>{s}</Text></View>
                    ))}
                  </View>
                </>
              )}
              {current.answer.avoid_pitfalls.length > 0 && (
                <>
                  <Text className='qa-ans-label'>避坑指南</Text>
                  {current.answer.avoid_pitfalls.map((p, i) => (
                    <View key={i} className='qa-pit'>⚠ {p}</View>
                  ))}
                </>
              )}
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
        <View className='sec-title'>📚 我的问答历史 <Text className='sec-note'>最近 3 条</Text></View>
      </View>
      {history.slice(0, 3).map((h) => (
        <View key={h.id} className='hist-row'>
          <QACard question={h.question} summary={`核心秘诀：${h.answer.core_secret}`} />
          <View className='hist-del' onClick={() => removeHistory(h.id)}>
            <View className='ic ic-trash ic-sm' />
          </View>
        </View>
      ))}
      {history.length === 0 && !loading && (
        <View className='note note--center'>还没有提问，问 AI 一个问题吧</View>
      )}
    </View>
  )
}
