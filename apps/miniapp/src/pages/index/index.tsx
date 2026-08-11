/**
 * 屏2 · 首页 小伴烹饪百科（原型 01）
 * 搜索框 + 猜你想问 + 今日小伴秘技 + 问答历史 + 收藏问答
 */
import { Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'
import QACard from '../../components/QACard'
import { addFavorite, askQAStream, deleteQARecord, fetchQAHistory, type QARecord } from '../../services/api'
import { useAuthStore } from '../../stores/auth'
import { useTabStore } from '../../stores/tab'
import { getSafeTop } from '../../utils/safeArea'
import './index.scss'

const HOT_QUESTIONS = [
  '红烧肉怎么做才能肥而不腻、入口即化',
  '蒸蛋怎么蒸才嫩滑没有蜂窝',
  '炖肉怎么去腥增香，肉质更软烂',
  '冰箱里的剩菜怎么变身新花样',
  '煎鱼怎么才能不破皮不粘锅',
  '青菜怎么炒才翠绿不变色',
  '天气太热了，推荐几道爽口的凉拌菜',
  '下班太累，推荐几道15分钟快手晚餐',
  '想吃辣，推荐几道香辣过瘾的下饭菜',
  '一个人住，一周的省事晚餐怎么安排',
  '减脂期晚餐吃什么，有肉有菜又不胖',
  '周末招待朋友，推荐一桌有面子的家常菜',
]

/* placeholder 断行：单行可显示约 14 字，长文案在逗号或 ~14 字处断成两行，避免截断 */
function wrapQuestion(q: string): string {
  if (q.length <= 14) return q
  const commaIdx = q.indexOf('，')
  // 有逗号且逗号在中间位置附近，在逗号后断行
  if (commaIdx > 4 && commaIdx < q.length - 4) {
    return `${q.slice(0, commaIdx + 1)}\n${q.slice(commaIdx + 1)}`
  }
  // 无合适逗号，按 14 字硬断
  return `${q.slice(0, 14)}\n${q.slice(14)}`
}

export default function Index() {
  const setTab = useTabStore((s) => s.setIndex)
  const [keyword, setKeyword] = useState('')
  const [current, setCurrent] = useState<QARecord | null>(null)
  const [history, setHistory] = useState<QARecord[]>([])
  const [loading, setLoading] = useState(false)
  const [typing, setTyping] = useState('') // 流式打字机文本
  const streamAbortRef = useRef<(() => void) | null>(null)
  /* 猜你想问轮播 placeholder */
  const [phIndex, setPhIndex] = useState(0)
  const phTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  /* 双击输入框填入当前轮播问题：记录上次点击时间，600ms 内再点一次视为双击 */
  const lastTapRef = useRef(0)

  useEffect(() => {
    phTimerRef.current = setInterval(() => {
      setPhIndex((i) => (i + 1) % HOT_QUESTIONS.length)
    }, 3000)
    return () => {
      if (phTimerRef.current) clearInterval(phTimerRef.current)
    }
  }, [])

  const onSearchTap = () => {
    // 已有输入则重置（用户手输时不触发）
    if (keyword.trim()) {
      lastTapRef.current = 0
      return
    }
    const now = Date.now()
    if (lastTapRef.current && now - lastTapRef.current < 600) {
      lastTapRef.current = 0
      setKeyword(HOT_QUESTIONS[phIndex]) // 双击 → 填入当前轮播问题
    } else {
      lastTapRef.current = now
    }
  }

  const onSearchInput = (v: string) => {
    setKeyword(v)
    lastTapRef.current = 0 // 用户手输时重置双击计时
  }

  useDidShow(() => {
    setTab(0)
    // 未登录不发起鉴权请求，直接去登录页
    if (!useAuthStore.getState().token) {
      Taro.reLaunch({ url: '/pages/login/index' })
      return
    }
    loadHistory()
  })

  useUnload(() => {
    if (streamAbortRef.current) streamAbortRef.current()
    streamAbortRef.current = null
  })

  const loadHistory = async () => {
    try {
      setHistory(await fetchQAHistory())
    } catch {
      /* 未登录/网络问题静默 */
    }
  }

  const ask = (q: string) => {
    const question = (q || keyword).trim()
    if (!question) return
    // 中断上一次未完成的流
    if (streamAbortRef.current) {
      streamAbortRef.current()
      streamAbortRef.current = null
    }
    setLoading(true)
    setTyping('')
    setCurrent(null)
    streamAbortRef.current = askQAStream(question, {
      onDelta: (text) => setTyping((prev) => prev + text),
      onDone: (rec) => {
        setTyping('')
        setCurrent(rec)
        setLoading(false)
        loadHistory()
        streamAbortRef.current = null
      },
      onError: (msg) => {
        setTyping('')
        setLoading(false)
        Taro.showToast({ title: msg || '提问失败', icon: 'none' })
        streamAbortRef.current = null
      },
    })
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
          placeholder={`问小伴：${wrapQuestion(HOT_QUESTIONS[phIndex])}${HOT_QUESTIONS[phIndex].endsWith('？') ? '' : '？'}`}
          placeholderClass='search-ph'
          autoHeight
          maxlength={500}
          onClick={onSearchTap}
          onInput={(e) => onSearchInput(e.detail.value)}
          onConfirm={() => ask(keyword)}
        />
        <View className={`sbtn ${keyword.trim() ? '' : 'sbtn--idle'}`} onClick={() => ask(keyword)}>
          <View className='ic ic-search--white ic-sm' />
        </View>
      </View>

      <View className='section'>
        <View className='sec-title'>
          🔥 今日小伴秘技
          {current && (
            <View className='more' onClick={() => ask(current.question)}>重新生成</View>
          )}
        </View>
      </View>

      {loading ? (
        <View className='bubble qa-answer typing-wrap'>
          <View className='qa-ans-head'>
            <Text className='qa-ans-q'>{typing || '小伴正在思考…'}</Text>
            <View className='typing-caret' />
          </View>
        </View>
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
          <Text>💡 输入一个厨艺问题，小伴会联网搜索并给出核心秘诀、步骤与避坑指南</Text>
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
        <View className='note note--center'>还没有提问，问小伴一个问题吧</View>
      )}
    </View>
  )
}
