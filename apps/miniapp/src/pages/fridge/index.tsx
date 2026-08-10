/**
 * 冰箱管家 · 食材过期预警（原型 04 屏6）：
 * 过期横幅 + 即将过期列表（做掉删除）+ AI 组合推荐 + 状态良好 + 添加食材
 */
import { Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'
import NavBar from '../../components/NavBar'
import {
  addFridgeItem,
  fetchFridge,
  fetchFridgeAdvice,
  removeFridgeItem,
  type FridgeAdvice,
  type FridgeItem,
} from '../../services/api'
import './index.scss'

const EMOJI_MAP: [string, string][] = [
  ['西红柿', '🍅'], ['番茄', '🍅'], ['鸡蛋', '🥚'], ['蛋', '🥚'], ['生菜', '🥬'],
  ['青菜', '🥬'], ['白菜', '🥬'], ['黄瓜', '🥒'], ['西兰花', '🥦'], ['土豆', '🥔'],
  ['胡萝卜', '🥕'], ['洋葱', '🧅'], ['大蒜', '🧄'], ['青椒', '🫑'], ['茄子', '🍆'],
  ['玉米', '🌽'], ['香菇', '🍄'], ['蘑菇', '🍄'], ['豆腐', '🫘'], ['牛奶', '🥛'],
  ['酸奶', '🥛'], ['猪肉', '🥩'], ['牛肉', '🥩'], ['羊肉', '🥩'], ['鸡肉', '🍗'],
  ['鸡翅', '🍗'], ['鸡胸肉', '🍗'], ['排骨', '🍖'], ['鱼', '🐟'], ['鲈鱼', '🐟'],
  ['虾', '🦐'], ['三文鱼', '🍣'], ['螃蟹', '🦀'], ['培根', '🥓'], ['火腿', '🍖'],
  ['香肠', '🌭'], ['面包', '🍞'], ['馒头', '🥟'], ['面条', '🍜'], ['挂面', '🍜'],
  ['米', '🍚'], ['大米', '🍚'], ['面粉', '🌾'], ['酱油', '🧂'], ['盐', '🧂'],
  ['油', '🫗'], ['苹果', '🍎'], ['香蕉', '🍌'], ['橙子', '🍊'], ['梨', '🍐'],
  ['草莓', '🍓'], ['葡萄', '🍇'], ['西瓜', '🍉'], ['柠檬', '🍋'], ['猕猴桃', '🥝'],
  ['桃子', '🍑'], ['火龙果', '🐉'], ['榴莲', '🫒'], ['芒果', '🥭'], ['菠萝', '🍍'],
]

function fridgeEmoji(name: string, stored: string): string {
  if (stored) return stored
  for (const [k, e] of EMOJI_MAP) {
    if (name.includes(k)) return e
  }
  return '🥘'
}

export default function FridgePage() {
  const [items, setItems] = useState<FridgeItem[]>([])
  const [loading, setLoading] = useState(false)
  const [advice, setAdvice] = useState<FridgeAdvice | null>(null)
  const [adviceLoading, setAdviceLoading] = useState(false)

  useDidShow(() => {
    load()
  })

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchFridge()
      setItems(data.items)
      if (data.expiring_count > 0) {
        loadAdvice()
      } else {
        setAdvice(null)
      }
    } catch (e: any) {
      Taro.showToast({ title: e.message || '加载失败', icon: 'none' })
    } finally {
      setLoading(false)
    }
  }

  const loadAdvice = async () => {
    setAdviceLoading(true)
    try {
      setAdvice(await fetchFridgeAdvice())
    } catch {
      /* 无临期食材或生成失败：不展示建议 */
      setAdvice(null)
    } finally {
      setAdviceLoading(false)
    }
  }

  const addItem = () => {
    Taro.showModal({
      title: '添加食材',
      editable: true,
      placeholderText: '输入食材名，如 西红柿',
      success: async (r) => {
        if (!r.confirm) return
        const name = (r.content || '').trim()
        if (!name) return
        try {
          await addFridgeItem({ name, emoji: fridgeEmoji(name, '') })
          Taro.showToast({ title: '已加入冰箱', icon: 'none' })
          load()
        } catch (e: any) {
          Taro.showToast({ title: e.message || '添加失败', icon: 'none' })
        }
      },
    })
  }

  const removeItem = (it: FridgeItem) => {
    Taro.showModal({
      title: '做掉「' + it.name + '」？',
      content: '做掉后将从冰箱移除，避免浪费、记入下次建议。',
      confirmText: '做掉',
      confirmColor: '#E8482A',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await removeFridgeItem(it.id)
          Taro.showToast({ title: '已做掉 ' + it.name, icon: 'none' })
          load()
        } catch (e: any) {
          Taro.showToast({ title: e.message || '操作失败', icon: 'none' })
        }
      },
    })
  }

  const expiring = items.filter((i) => i.status === 'now' || i.status === 'warn')
  const fresh = items.filter((i) => i.status === 'ok')

  if (!loading && items.length === 0) {
    return (
      <View className='page-content fridge'>
        <NavBar title='冰箱管家' showBack />
        <View className='empty'>
          <View className='empty-art'>🧊</View>
          <Text className='empty-title'>冰箱空空如也</Text>
          <Text className='empty-desc'>把放进冰箱的食材记下来，AI 帮你盯着保质期</Text>
          <View className='btn btn--red btn--block' onClick={addItem}>
            <Text>＋ 添加食材</Text>
          </View>
        </View>
      </View>
    )
  }

  return (
    <View className='page-content fridge'>
      <NavBar title='冰箱管家' showBack />

      {expiring.length > 0 ? (
        <View className='exp-banner'>
          <View className='eb-ic'><View className='ic ic-bell' /></View>
          <View className='eb-body'>
            <Text className='eb-title'>{expiring.length} 项食材快过期啦</Text>
            <Text className='eb-sub'>建议今天做掉，避免浪费</Text>
          </View>
        </View>
      ) : (
        <View className='exp-banner exp-banner--ok'>
          <View className='eb-ic eb-ic--green'><View className='ic ic-check' /></View>
          <View className='eb-body'>
            <Text className='eb-title'>冰箱状态良好</Text>
            <Text className='eb-sub'>暂无临期食材，继续保持</Text>
          </View>
        </View>
      )}

      {expiring.length > 0 && (
        <View className='section'>
          <View className='sec-title'><Text>⏳ 即将过期</Text></View>
          {expiring.map((it) => (
            <View key={it.id} className='fridge-item'>
              <View className='fi-ic'><Text>{fridgeEmoji(it.name, it.emoji)}</Text></View>
              <View className='fi-body'>
                <Text className='fi-name'>{it.name}</Text>
                <Text className='fi-note'>已放 {it.days_stored} 天</Text>
              </View>
              <View className={`exp-tag exp-tag--${it.status}`}>
                <Text>{it.status === 'now' ? '今日清空' : `还 ${it.days_left} 天`}</Text>
              </View>
              <View className='fi-cta' onClick={() => removeItem(it)}><Text>做掉</Text></View>
            </View>
          ))}
        </View>
      )}

      <View className='section'>
        <View className='sec-title'><Text>💡 AI 建议</Text></View>
        {adviceLoading ? (
          <View className='advice-loading'><Text>AI 分析临期食材中…</Text></View>
        ) : advice ? (
          <View className='bubble advice-bubble'>
            <View className='star-burst star-burst--sm'><Text>组合推荐</Text></View>
            {advice.suggestions.map((s, idx) => (
              <View key={idx} className='advice-line'>
                <Text>
                  {s.ingredients.join(' + ')} → <Text className='advice-dish'>{s.dish}</Text>
                  <Text className='advice-meta'>（{s.time_minutes} 分钟 · 匹配 {s.match_score}%）</Text>
                </Text>
              </View>
            ))}
            {advice.note && <Text className='advice-note'>{advice.note}</Text>}
          </View>
        ) : (
          <View className='advice-empty'><Text>没有临期食材时，不需要组合推荐</Text></View>
        )}
      </View>

      {fresh.length > 0 && (
        <View className='section'>
          {fresh.map((it) => (
            <View key={it.id} className='fridge-item'>
              <View className='fi-ic'><Text>{fridgeEmoji(it.name, it.emoji)}</Text></View>
              <View className='fi-body'>
                <Text className='fi-name'>{it.name}</Text>
                <Text className='fi-note'>已放 {it.days_stored} 天 · 状态良好</Text>
              </View>
              <View className={`exp-tag exp-tag--${it.status}`}>
                <Text>还 {it.days_left} 天</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <View className='fridge-add'>
        <View className='btn btn--red btn--block' onClick={addItem}>
          <Text>＋ 添加食材</Text>
        </View>
      </View>
    </View>
  )
}
